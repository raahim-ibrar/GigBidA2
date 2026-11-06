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
from agent.mcp_client import build_client
from agent.memory.service import MemoryService, MemoryUnavailable
from agent.model_client import BudgetExceeded, ModelUnavailable, OllamaModels
from agent.portfolio_client import PortfolioMCP
from agent.proposal_nodes import GroundingFailure, ProposalNodes, ReviewRequired
from agent.run_store import LostWorkerLease, RunConflict, RunStore
from agent.workspace_client import WorkspaceMCP


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
):
    store, token, config = RunStore(engine), str(uuid4()), AgentConfig()
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
                return {"status": "drafted"}
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
                                    "MODEL_CACHE_DIR": str(settings.model_cache_dir),
                                },
                            }
                        }
                    )
                    reader = PortfolioMCP(
                        await stack.enter_async_context(client.session("portfolio"))
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
                            await stack.enter_async_context(workspace_client.session("workspace"))
                        )
                    business = ConversationNodes(
                        models, reader, workspace, config, load_memory=memory
                    )
                else:
                    business = ProposalNodes(
                        models, reader, config, execute_local=execute, load_memory=memory
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
                    )
                )
                snapshot = await graph.aget_state(thread)
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
                    graph_input = None if snapshot.values else claimed["snapshot"]
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
                return {"status": "drafted"}
            safe = (BudgetExceeded, ModelUnavailable, GroundingFailure, ReviewRequired, RunConflict)
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
            await asyncio.to_thread(store.fail, tenant, run_id, token, message)
            return {"status": "needs_attention", "error_types": kinds}


# Existing worker jobs and integration callers retain their entry point.
process_bid = process_run
