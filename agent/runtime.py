"""Worker-owned Postgres graph lifecycle. API requests only save and enqueue work."""

import asyncio
import hashlib
import sys
from contextlib import AsyncExitStack
from uuid import uuid4

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.errors import NodeCancelledError
from langgraph.types import Command

from agent import handoffs
from agent.config import AgentConfig
from agent.conversation_nodes import ConversationNodes
from agent.graphs.bid_graph import build_bid_graph
from agent.graphs.conversation_graph import build_conversation_graph
from agent.marketplace_client import MarketplaceMCP
from agent.mcp_client import build_client
from agent.memory.service import MemoryService, MemoryUnavailable
from agent.model_client import BudgetExceeded, ModelUnavailable, OllamaModels
from agent.portfolio_client import PortfolioMCP
from agent.proposal_nodes import GroundingFailure, ProposalNodes, ReviewRequired
from agent.run_store import LostWorkerLease, RunConflict, RunStore
from agent.tracing import TracedSession
from agent.workspace_client import WorkspaceMCP
from mcp_servers.marketplace.adapters.student_sim import MarketplaceRejected, MarketplaceUnavailable


def lock_key(value):
    return int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], "big", signed=True)


def checkpoint_serializer():
    classes = [
        ("agent.handoffs", name)
        for name, value in vars(handoffs).items()
        if isinstance(value, type) and issubclass(value, handoffs.Contract)
    ]
    return JsonPlusSerializer(pickle_fallback=False, allowed_msgpack_modules=classes)


def leaf_errors(error):
    if isinstance(error, BaseExceptionGroup):
        return [leaf for child in error.exceptions for leaf in leaf_errors(child)]
    return [error]


async def process_run(
    engine,
    settings,
    tenant,
    run_id,
    *,
    models_factory=OllamaModels,
    portfolio_reader=None,
    workspace_reader=None,
    marketplace_reader=None,
    config=None,
):
    store, token, config = (
        RunStore(engine),
        str(uuid4()),
        config or AgentConfig(profile_name=settings.model_profile),
    )
    if models_factory is OllamaModels and config.profile.get("provider") == "groq":
        from agent.providers.groq import GroqModels

        models_factory = GroqModels
    if models_factory is OllamaModels and config.profile.get("provider") == "gemini":
        from agent.providers.gemini import GeminiModels

        models_factory = GeminiModels
    dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    thread = {
        "configurable": {"thread_id": f"{tenant}:{run_id}"},
        "recursion_limit": config.budgets.max_steps + 5,
    }
    async with AsyncPostgresSaver.from_conn_string(dsn, serde=checkpoint_serializer()) as saver:
        # The same session owns checkpoints and the advisory lock. Disconnecting
        # releases the lock and prevents a stale process from publishing checkpoints.
        cursor = await saver.conn.execute(
            "SELECT pg_try_advisory_lock(%s) AS locked", (lock_key(f"bid:{tenant}:{run_id}"),)
        )
        if not (await cursor.fetchone())["locked"]:
            return {"status": "already_running"}
        claimed = await asyncio.to_thread(store.claim, tenant, run_id, token)
        if claimed is None:
            return {"status": "not_pending"}
        try:
            if await asyncio.to_thread(store.recover_local, tenant, run_id, token):
                return {"status": (await asyncio.to_thread(store.run, tenant, run_id)).status}
            # API/worker startup owns schema migrations. Never create concurrent
            # indexes while another run/request can hold a blocking snapshot.

            async def record(metrics):
                await asyncio.to_thread(store.event, tenant, run_id, token, "model_usage", metrics)

            async def reserve(amount):
                await asyncio.to_thread(
                    store.reserve,
                    tenant,
                    run_id,
                    token,
                    amount,
                    config.budgets.max_tokens_per_thread,
                )

            async def settle(reserved, charged):
                await asyncio.to_thread(store.settle, tenant, run_id, token, reserved, charged)

            async def execute(state):
                result = await asyncio.to_thread(store.save_local, tenant, run_id, token, state)
                return result.model_dump(mode="json")

            async def memory():
                try:
                    service = MemoryService(engine, settings.database_url)
                    await asyncio.to_thread(service.ensure)
                    context = await asyncio.to_thread(service.context, tenant)
                    await asyncio.to_thread(
                        store.event,
                        tenant,
                        run_id,
                        token,
                        "memory_loaded",
                        {
                            "style_count": len(context["style_preferences"]),
                            "outcome_count": len(context["outcome_patterns"]),
                        },
                    )
                    return context
                except MemoryUnavailable:
                    await asyncio.to_thread(
                        store.event, tenant, run_id, token, "memory_unavailable", {}
                    )
                    return {}

            models = models_factory(
                settings.ollama_base_url,
                config,
                record=record,
                tokens_used=claimed["tokens"],
                reserve_budget=reserve,
                settle_budget=settle,
            )
            async with AsyncExitStack() as stack:
                marketplace = marketplace_reader
                if claimed["snapshot"].get("raw_job", {}).get("source") not in {
                    "student_sim",
                    "upwork",
                }:
                    marketplace = None
                if (
                    claimed["snapshot"].get("raw_job", {}).get("source")
                    in {"student_sim", "upwork"}
                    and marketplace is None
                ):
                    market_client = build_client(
                        {
                            "marketplace": {
                                "transport": "stdio",
                                "command": sys.executable,
                                "args": ["-m", "mcp_servers.marketplace.server"],
                                "env": {
                                    "GIGBID_TENANT_ID": tenant,
                                    "GIGBID_RUN_ID": run_id,
                                    "DATABASE_URL": settings.database_url,
                                    "OAUTH_ENCRYPTION_KEY": (
                                        settings.oauth_encryption_key.get_secret_value()
                                    ),
                                    "STUDENT_SIM_URL": settings.student_sim_url,
                                    "STUDENT_SIM_API_KEY": settings.student_sim_api_key,
                                },
                            }
                        }
                    )
                    marketplace = MarketplaceMCP(
                        TracedSession(
                            await stack.enter_async_context(market_client.session("marketplace")),
                            store,
                            tenant,
                            run_id,
                            token,
                            "marketplace",
                        )
                    )
                reader = portfolio_reader
                if reader is None:
                    client = build_client(
                        {
                            "portfolio": {
                                "transport": "stdio",
                                "command": sys.executable,
                                "args": ["-m", "mcp_servers.portfolio.server"],
                                "env": {
                                    "GIGBID_TENANT_ID": tenant,
                                    "DATABASE_URL": settings.database_url,
                                    "QDRANT_URL": settings.qdrant_url,
                                    "GIGBID_RUN_ID": run_id,
                                    "MODEL_CACHE_DIR": str(settings.model_cache_dir),
                                },
                            }
                        }
                    )
                    reader = PortfolioMCP(
                        TracedSession(
                            await stack.enter_async_context(client.session("portfolio")),
                            store,
                            tenant,
                            run_id,
                            token,
                            "portfolio",
                        )
                    )
                if claimed["kind"] == "conversation":
                    workspace = workspace_reader
                    if workspace is None:
                        workspace_client = build_client(
                            {
                                "workspace": {
                                    "transport": "stdio",
                                    "command": sys.executable,
                                    "args": ["-m", "mcp_servers.workspace.server"],
                                    "env": {
                                        "GIGBID_TENANT_ID": tenant,
                                        "GIGBID_RUN_ID": run_id,
                                        "DATABASE_URL": settings.database_url,
                                    },
                                }
                            }
                        )
                        workspace = WorkspaceMCP(
                            TracedSession(
                                await stack.enter_async_context(
                                    workspace_client.session("workspace")
                                ),
                                store,
                                tenant,
                                run_id,
                                token,
                                "workspace",
                            )
                        )
                    business = ConversationNodes(
                        models,
                        reader,
                        workspace,
                        config,
                        load_memory=memory,
                        marketplace=marketplace,
                    )
                else:
                    business = ProposalNodes(
                        models,
                        reader,
                        config,
                        execute_local=execute,
                        load_memory=memory,
                        marketplace=marketplace,
                    )

                def bounded(name, function):
                    async def node(state):
                        await asyncio.to_thread(
                            store.step, tenant, run_id, token, name, config.budgets.max_steps
                        )
                        result = await function(state)
                        await asyncio.to_thread(
                            store.event, tenant, run_id, token, "node_completed", {"node": name}
                        )
                        return result

                    return node

                bounded_nodes = {
                    name: bounded(name, function) for name, function in business.mapping().items()
                }
                graph = (
                    build_conversation_graph(checkpointer=saver, nodes=bounded_nodes)
                    if claimed["kind"] == "conversation"
                    else build_bid_graph(
                        checkpointer=saver,
                        nodes=bounded_nodes,
                        max_revisions=config.budgets.max_critic_revisions,
                        entry_node=claimed["snapshot"]
                        .get("replay_request", {})
                        .get("effective_node", "scout"),
                    )
                )
                snapshot = await graph.aget_state(thread)
                initial = claimed["snapshot"]
                if not snapshot.values and initial.get("replay_request"):
                    request = initial["replay_request"]
                    parent_config = {
                        "configurable": {
                            "thread_id": f"{tenant}:{request['parent_run_id']}",
                            "checkpoint_id": request["checkpoint_id"],
                        }
                    }
                    parent = await graph.aget_state(parent_config)
                    if not parent.values:
                        raise RunConflict("Replay source checkpoint no longer exists")
                    # Reuse typed state from the saver, but never inherit approval,
                    # write receipts, preview keys or token/step counters.
                    initial = {
                        **parent.values,
                        **initial,
                        "events": [],
                        "revisions": 0,
                        "status": "queued",
                        "user_edited": False,
                    }
                    for field in ("approval", "preview", "provider_result", "verification"):
                        initial.pop(field, None)
                fresh_messages = claimed["kind"] == "conversation" and (
                    snapshot.values.get("source_revision") != claimed["snapshot"]["source_revision"]
                )
                resume = claimed["resume"]
                pending_ids = {item.id for item in snapshot.interrupts}
                if fresh_messages:
                    graph_input = claimed["snapshot"]
                elif resume and resume["interrupt_id"] in pending_ids:
                    graph_input = Command(resume={resume["interrupt_id"]: resume["decision"]})
                elif snapshot.interrupts or (snapshot.values and not snapshot.next):
                    graph_input = None
                else:
                    graph_input = None if snapshot.values else initial
                # An already paused/finished checkpoint needs only DB reconciliation.
                run_graph = not snapshot.values or bool(snapshot.next and not snapshot.interrupts)
                run_graph = run_graph or isinstance(graph_input, Command) or fresh_messages
                if run_graph:
                    async for state in graph.astream(graph_input, thread, stream_mode="values"):
                        await asyncio.to_thread(store.save, tenant, run_id, token, state)
                snapshot = await graph.aget_state(thread)
                if snapshot.next and not snapshot.interrupts:
                    # A cancelled node can end the stream without raising. Keep the
                    # run pending so a replacement worker resumes its checkpoint.
                    raise asyncio.CancelledError("Graph stopped with unfinished checkpoint tasks")
                if len(snapshot.interrupts) > 1:
                    raise ReviewRequired("Multiple review requests require manual investigation")
                review = None
                if snapshot.interrupts:
                    pause = snapshot.interrupts[0]
                    review = {**pause.value, "interrupt_id": pause.id}
                await asyncio.to_thread(
                    store.save, tenant, run_id, token, snapshot.values, review, complete=True
                )
                await asyncio.to_thread(store.finish, tenant, run_id, token)
                return {"status": "awaiting_approval" if review else snapshot.values.get("status")}
        except NodeCancelledError:
            raise asyncio.CancelledError(
                "Graph node was cancelled; resume its checkpoint"
            ) from None
        except LostWorkerLease:
            return {"status": "superseded"}
        except Exception as error:
            if any(isinstance(item, LostWorkerLease) for item in leaf_errors(error)):
                return {"status": "superseded"}
            if await asyncio.to_thread(store.recover_local, tenant, run_id, token):
                return {"status": (await asyncio.to_thread(store.run, tenant, run_id)).status}
            safe = (
                BudgetExceeded,
                ModelUnavailable,
                GroundingFailure,
                ReviewRequired,
                RunConflict,
                MarketplaceUnavailable,
                MarketplaceRejected,
            )
            leaves = leaf_errors(error)
            known = [str(item) for item in leaves if isinstance(item, safe)]
            kinds = list(dict.fromkeys(type(item).__name__ for item in leaves))
            await asyncio.to_thread(
                store.event, tenant, run_id, token, "runtime_error", {"error_types": kinds}
            )
            message = (
                " ".join(known)
                if known
                else (
                    "Run unavailable. Check the worker, local models, MCP and portfolio evidence."
                )
            )
            await asyncio.to_thread(
                store.fail,
                tenant,
                run_id,
                token,
                message,
                retryable=bool(leaves)
                and all(
                    isinstance(
                        item,
                        (ModelUnavailable, MarketplaceUnavailable, ConnectionError, TimeoutError),
                    )
                    for item in leaves
                ),
            )
            return {"status": "needs_attention", "error_types": kinds}


# Existing worker jobs and integration callers retain their entry point.
process_bid = process_run
