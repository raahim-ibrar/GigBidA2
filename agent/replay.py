"""Owner-scoped immutable checkpoint inspection and safe replay forks."""

import asyncio
import os
from uuid import UUID, uuid4

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agent.graphs.bid_graph import BUSINESS_NODES, build_bid_graph
from agent.run_store import RunConflict, RunNotFound
from apps.api.models import AgentRun, FreelancerProfile, JobRecord


def effective_node(node):
    if node not in {*BUSINESS_NODES, "approval"}:
        raise RunConflict("Unknown bid graph node")
    if node in {"analyst", "risk", "matcher"}:
        return "scout"
    if node in {"critic", "compliance", "preview", "execute", "approval"}:
        return "verifier"
    if node == "regenerate":
        return "writer"
    return node


async def _checkpoints(engine, settings, tenant, run_id, checkpoint_id=None):
    from agent.runtime import checkpoint_serializer

    with Session(engine) as db:
        run = db.get(AgentRun, run_id)
        if not run or run.user_id != tenant:
            raise RunNotFound("Run not found")
        if run.kind != "bid":
            raise RunConflict(
                "Checkpoint replay is available for bid jobs; "
                "conversation replies keep their current message revision"
            )
    dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    config = {"configurable": {"thread_id": f"{tenant}:{run_id}"}}
    if checkpoint_id:
        config["configurable"]["checkpoint_id"] = str(UUID(checkpoint_id))
    async with AsyncPostgresSaver.from_conn_string(dsn, serde=checkpoint_serializer()) as saver:
        graph = build_bid_graph(checkpointer=saver)
        if checkpoint_id:
            snapshot = await graph.aget_state(config)
            if not snapshot.values:
                raise RunNotFound("Checkpoint not found")
            return snapshot
        return [
            {
                "checkpoint_id": s.config["configurable"]["checkpoint_id"],
                "created_at": s.created_at,
                "next_nodes": list(s.next),
                "step": s.metadata.get("step") if s.metadata else None,
            }
            async for s in graph.aget_state_history(config, limit=100)
        ]


async def checkpoints(*args, **kwargs):
    if os.name == "nt":

        def run():
            with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as loop:
                return loop.run(_checkpoints(*args, **kwargs))

        return await asyncio.to_thread(run)
    return await _checkpoints(*args, **kwargs)


async def fork(engine, settings, store, tenant, parent, body):
    await checkpoints(engine, settings, tenant, parent, str(body.checkpoint_id))
    request = {
        "parent_run_id": parent,
        "checkpoint_id": str(body.checkpoint_id),
        "requested_node": body.node,
        "effective_node": effective_node(body.node),
    }
    identity = None
    try:
        with Session(engine) as db, db.begin():
            query = select(AgentRun).where(
                AgentRun.user_id == tenant, AgentRun.request_key == str(body.idempotency_key)
            )
            row = db.scalar(query)
            if row:
                if row.snapshot.get("replay_request") != request:
                    raise RunConflict("This request key belongs to another operation")
                identity = row.id
            else:
                source = db.get(AgentRun, parent)
                if not source or source.user_id != tenant:
                    raise RunNotFound("Run not found")
                job = db.get(JobRecord, source.job_id)
                profile = db.get(FreelancerProfile, tenant)
                identity = str(uuid4())
                row = AgentRun(
                    id=identity,
                    user_id=tenant,
                    job_id=job.id,
                    request_key=str(body.idempotency_key),
                    kind="bid",
                    snapshot={
                        "run_id": identity,
                        "tenant_id": tenant,
                        "job_id": job.id,
                        "raw_job": job.raw,
                        "preferences": {
                            "hourly_floor": str(profile.hourly_floor) if profile else "15"
                        },
                        "replay_request": request,
                        "events": [],
                    },
                )
                db.add(row)
                store._event(db, row, "queued", {"replay_parent": parent})
    except IntegrityError:
        with Session(engine) as db:
            row = db.scalar(
                select(AgentRun).where(
                    AgentRun.user_id == tenant, AgentRun.request_key == str(body.idempotency_key)
                )
            )
            if not row or row.snapshot.get("replay_request") != request:
                raise RunConflict("Concurrent replay request has different parameters") from None
            identity = row.id
    return store.run(tenant, identity)
