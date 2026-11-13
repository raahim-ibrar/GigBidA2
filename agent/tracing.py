"""Explicit metadata-only LangSmith export from the durable, tenant-scoped audit trail.

No prompts, documents, tool arguments/results, user identities or exception messages
leave the application. Automatic SDK tracing is not required or enabled here.
"""

from copy import deepcopy
from datetime import UTC, timedelta
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.costs import money, valid_tokens
from agent.run_store import RunNotFound
from apps.api.models import AgentRun, RunEvent


class TracedSession:
    def __init__(self, session, store, tenant, run_id, token, server):
        self.session, self.store, self.tenant = session, store, tenant
        self.run_id, self.token, self.server = run_id, token, server

    def __getattr__(self, name):
        return getattr(self.session, name)

    async def call_tool(self, name, *args, **kwargs):
        import asyncio
        import time

        start, ok = time.perf_counter(), False
        try:
            result = await self.session.call_tool(name, *args, **kwargs)
            ok = not result.isError
            return result
        finally:
            await asyncio.to_thread(
                self.store.event,
                self.tenant,
                self.run_id,
                self.token,
                "mcp_call",
                {
                    "server": self.server,
                    "tool": name,
                    "ok": ok,
                    "elapsed_seconds": time.perf_counter() - start,
                },
            )


def stamp(value):
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def build_spans(run, events):
    """Reconstruct measured intervals only; raw audit details are never copied."""
    root_id = UUID(run.id)
    root_order = stamp(run.created_at) + str(root_id)
    root = {
        "id": str(root_id),
        "trace_id": str(root_id),
        "name": "GigBid " + run.kind,
        "run_type": "chain",
        "start_time": run.created_at,
        "end_time": run.updated_at,
        "dotted_order": root_order,
        "inputs": {"content": "omitted for privacy"},
        "outputs": {"status": run.status, "steps": run.steps, "tokens": run.tokens},
        "extra": {"metadata": {"trace_id": run.id, "export_policy": "metadata-only-v1"}},
    }
    spans, nodes = [root], []
    for event in events:
        if event.kind != "recovery_observed":
            continue
        # Host-observed recovery metadata only. Never export arbitrary audit payloads.
        elapsed = max(0, min(float(event.details.get("elapsed_seconds", 0)), 3600))
        start = event.created_at - timedelta(seconds=elapsed)
        identity = str(uuid5(root_id, "recovery:" + str(event.id)))
        spans.append(
            {
                "id": identity,
                "trace_id": run.id,
                "parent_run_id": run.id,
                "name": "control:api_restart",
                "run_type": "chain",
                "start_time": start,
                "end_time": event.created_at,
                "dotted_order": root_order + "." + stamp(start) + identity,
                "inputs": {},
                "outputs": {
                    "process_exit_observed": event.details.get("process_exit_observed") is True,
                    "readiness_observed": event.details.get("readiness_observed") is True,
                },
            }
        )
    for event in events:
        if event.kind != "node_started":
            continue
        end = next(
            (
                e.created_at
                for e in events
                if e.id > event.id
                and (
                    e.kind == "node_started"
                    or (
                        e.kind == "node_completed"
                        and e.details.get("node") == event.details.get("node")
                    )
                )
            ),
            run.updated_at,
        )
        identity = str(uuid5(root_id, "node:" + str(event.id)))
        node = {
            "id": identity,
            "trace_id": run.id,
            "parent_run_id": run.id,
            "name": "node:" + str(event.details.get("node", "unknown")),
            "run_type": "chain",
            "start_time": event.created_at,
            "end_time": end,
            "dotted_order": root_order + "." + stamp(event.created_at) + identity,
            "inputs": {},
            "outputs": {"audit_event_id": event.id},
        }
        spans.append(node)
        nodes.append(node)
    for event in events:
        if event.kind not in {"model_usage", "mcp_call"}:
            continue
        details = event.details
        elapsed = max(0, min(float(details.get("elapsed_seconds", 0)), 3600))
        start = event.created_at - timedelta(seconds=elapsed)
        parent = next(
            (
                node
                for node in reversed(nodes)
                if node["start_time"] <= event.created_at <= node["end_time"]
            ),
            root,
        )
        identity = str(uuid5(root_id, "event:" + str(event.id)))
        is_llm = event.kind == "model_usage"
        # Names come from host-controlled roles and registered tools, not source documents.
        name = (
            "model:" + str(details.get("role", "unknown"))
            if is_llm
            else "mcp:"
            + str(details.get("server", "unknown"))
            + "."
            + str(details.get("tool", "unknown"))
        )
        metadata = {"audit_event_id": event.id, "trace_id": run.id}
        outputs = {"ok": details.get("ok", True)}
        if is_llm:
            inputs, output = (
                details["input_tokens"] if valid_tokens(details) else 0,
                details["output_tokens"] if valid_tokens(details) else 0,
            )
            metadata.update(
                ls_provider=details.get("provider", "unknown"),
                ls_model_name=details.get("model", "unknown"),
                cost_known=money(details.get("usd")) is not None,
                estimated_cost_known=money(details.get("estimated_usd")) is not None,
            )
            if valid_tokens(details):
                outputs["usage_metadata"] = {
                    "input_tokens": inputs,
                    "output_tokens": output,
                    "total_tokens": inputs + output,
                }
            outputs["usage_known"] = valid_tokens(details)
            for field in ("usd", "estimated_usd"):
                amount = money(details.get(field))
                outputs[field] = float(amount) if amount is not None else None
        spans.append(
            {
                "id": identity,
                "trace_id": run.id,
                "parent_run_id": parent["id"],
                "name": name,
                "run_type": "llm" if is_llm else "tool",
                "start_time": start,
                "end_time": event.created_at,
                "dotted_order": parent["dotted_order"] + "." + stamp(start) + identity,
                "inputs": {"content": "omitted for privacy"},
                "outputs": outputs,
                "extra": {"metadata": metadata},
            }
        )
    return spans


def export_run(engine, settings, tenant, run_id, *, client=None):
    if not settings.trace_export_enabled:
        return {"trace_id": run_id, "status": "disabled"}
    with Session(engine) as db:
        run = db.scalar(select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == tenant))
        if run is None:
            raise RunNotFound("Run not found")
        events = list(
            db.scalars(select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.id))
        )
        source = [e for e in events if not e.kind.startswith("trace_")]
        cursor = max((e.id for e in source), default=0)
        prior = next((e.details for e in reversed(events) if e.kind == "trace_exported"), {})
        policy = "immutable-snapshot-v2"
        if prior.get("cursor") == cursor and prior.get("policy") == policy:
            return prior
        spans = build_spans(run, source)
        # Some trace services reject repeated patches to a closed span. Export an
        # immutable snapshot per audit cursor instead. Every span retains the same
        # GigBid correlation ID in metadata; the vendor ID identifies this snapshot.
        remote_root = str(uuid5(UUID(run.id), f"{policy}:{cursor}"))
        identities = {
            span["id"]: remote_root
            if span["id"] == run.id
            else str(uuid5(UUID(remote_root), span["id"]))
            for span in spans
        }
        for span in spans:
            old = span["id"]
            span["id"] = identities[old]
            span["trace_id"] = remote_root
            if span.get("parent_run_id"):
                span["parent_run_id"] = identities[span["parent_run_id"]]
            order = span["dotted_order"]
            for original, replacement in identities.items():
                order = order.replace(original, replacement)
            span["dotted_order"] = order
            span.setdefault("extra", {}).setdefault("metadata", {}).update(
                trace_id=run.id, export_policy=policy, audit_cursor=cursor
            )
        if client is None:
            from langsmith import Client

            client = Client(
                api_key=settings.langsmith_api_key.get_secret_value(),
                api_url="https://api.smith.langchain.com",
                auto_batch_tracing=False,
            )
        client.batch_ingest_runs(
            create=[{**deepcopy(s), "session_name": settings.langsmith_project} for s in spans],
            update=[],
        )
        result = {
            "trace_id": run_id,
            "remote_trace_id": remote_root,
            "policy": policy,
            "status": "exported",
            "cursor": cursor,
            # LangSmith may normalize update dictionaries in place to UUID objects.
            # Persist JSON primitives even after the SDK has touched those objects.
            "span_ids": [str(s["id"]) for s in spans],
            "spans": len(spans),
        }
        db.add(RunEvent(run_id=run_id, kind="trace_exported", details=result))
        db.commit()
        return result


def trace_summary(engine, tenant, run_id):
    with Session(engine) as db:
        run = db.scalar(select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == tenant))
        if run is None:
            raise RunNotFound("Run not found")
        events = list(
            db.scalars(
                select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.id.desc())
            )
        )
        exported = next((e.details for e in events if e.kind == "trace_exported"), {})
        public = next((e.details.get("url") for e in events if e.kind == "trace_shared"), None)
        return {
            "trace_id": run_id,
            "status": exported.get("status", "not_exported"),
            "spans": exported.get("spans", 0),
            "public_url": public,
            "remote_trace_id": exported.get("remote_trace_id", run_id),
        }
