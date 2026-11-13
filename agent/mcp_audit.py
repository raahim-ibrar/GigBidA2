"""Local, tenant-bound MCP read receipts. Raw source text never reaches storage."""

import asyncio
import inspect
import json
import math
import time
from functools import wraps
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.run_store import RunNotFound
from apps.api.models import AgentRun, MCPReadAudit, User, utcnow

# Unknown keys can themselves contain names, emails, tokens or requirements.
# Keep only reviewed schema labels; arbitrary mapping keys become field ordinals.
FIELDS = set(
    """request arguments params action query requirement k limit variant filters
id job_id client_id conversation_id source type text content data items skills
structuredContent isError result error kind message record client balance connects
connectsBalance total count has_more hasMore next_cursor currency billing_type
budget_min budget_max amount median p25 p75 market synthetic payment_verified
completed_projects average_rating requirements deliverables screening_questions
required_skills title description evidence_ids document_id page project date
outcome persona client_industry score distance start end slots timezone duration_minutes
available windows excluded duration minutes total_count source_revision source_digest
provenance base_text dataset dataset_version license notice simulation_context
limitations metadata resource uri mimeType blob annotations readOnlyHint
destructiveHint idempotentHint openWorldHint org_uid authorization access_token
refresh_token api_key password client_secret email phone url name token secret
""".split()
)
SENSITIVE = set(
    """org_uid authorization access_token refresh_token api_key password
client_secret email phone token secret source_digest""".split()
)
NUMBERS = set(
    """k limit connects connectsBalance total count budget_min budget_max amount
median p25 p75 completed_projects average_rating score distance page duration_minutes
duration minutes total_count source_revision""".split()
)
ENUMS = {
    "currency": {"USD"},
    "billing_type": {"hourly", "fixed", "unknown"},
    "source": {
        "upwork",
        "student_sim",
        "manual",
        "historical_posted_budgets",
        "synthetic_posted_budgets",
        "synthetic_client_posted_budgets",
        "unavailable_live_client_price_history",
    },
    "type": {"text", "image", "audio", "resource", "resource_link", "case_study", "proposal"},
    "variant": {"v0", "v3", "v8"},
}


def redact_payload(value):
    """Bounded structural audit: retain safe scalars, suppress every free-form string.

    This intentionally goes beyond regex PII masking: CVs, prompts, filenames,
    arbitrary secrets, dynamic keys and binary payloads are withheld by default.
    """
    remaining = 256

    def visit(item, key="", depth=0):
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > 8:
            return "[truncated]"
        if key in SENSITIVE:
            return "[redacted]"
        if hasattr(item, "model_dump"):
            item = item.model_dump(mode="json", exclude_none=True)
        if item is None or isinstance(item, bool):
            return item
        if isinstance(item, (int, float)):
            return item if key in NUMBERS and math.isfinite(item) else "[redacted number]"
        if isinstance(item, str):
            if item in ENUMS.get(key, set()):
                return item
            # Some MCP servers supply JSON only in a text content block.
            if key == "text" and len(item) <= 65536 and item.lstrip().startswith(("{", "[")):
                try:
                    return {"redacted_json": visit(json.loads(item), depth=depth + 1)}
                except (ValueError, RecursionError):
                    pass
            return "[redacted text]"
        if isinstance(item, dict):
            result = {}
            for index, (name, child) in enumerate(item.items()):
                if index >= 40 or remaining <= 0:
                    result["_truncated"] = True
                    break
                if isinstance(name, str) and name in FIELDS:
                    result[name] = visit(child, name, depth + 1)
                else:
                    result[f"_private_field_{index}"] = "[redacted]"
            return result
        if isinstance(item, (list, tuple)):
            result = [visit(child, key, depth + 1) for child in item[:20]]
            if len(item) > 20:
                result.append("[truncated]")
            return result
        return "[redacted object]"

    result = visit(value)
    if len(json.dumps(result, ensure_ascii=True)) > 32768:
        return {"_truncated": True}
    return result


class MCPAuditUnavailable(RuntimeError):
    pass


class ReadAuditor:
    def __init__(self, engine, tenant, run_id=None):
        self.engine, self.tenant, self.run_id = engine, tenant, run_id

    def start(self, server, tool, arguments):
        with Session(self.engine) as db, db.begin():
            if not self.tenant or db.get(User, self.tenant) is None:
                raise RunNotFound("MCP audit account not found")
            if self.run_id:
                run = db.get(AgentRun, self.run_id)
                if not run or run.user_id != self.tenant:
                    raise RunNotFound("MCP audit run not found")
            identity = str(uuid4())
            db.add(
                MCPReadAudit(
                    id=identity,
                    user_id=self.tenant,
                    run_id=self.run_id,
                    server=server,
                    tool=tool,
                    status="started",
                    arguments=redact_payload(arguments),
                )
            )
            return identity

    def finish(self, identity, status, result, elapsed):
        with Session(self.engine) as db, db.begin():
            row = db.scalar(
                select(MCPReadAudit)
                .where(
                    MCPReadAudit.id == identity,
                    MCPReadAudit.user_id == self.tenant,
                )
                .with_for_update()
            )
            if row is None:
                raise RunNotFound("MCP audit not found")
            if row.status != "started":
                raise MCPAuditUnavailable("MCP read receipt already finalized")
            row.status, row.result = status, redact_payload(result)
            row.elapsed_seconds, row.finished_at = elapsed, utcnow()

    async def invoke(self, server, tool, arguments, operation):
        # Commit the attempt before reading. Audit failure blocks dispatch/return.
        try:
            identity = await asyncio.to_thread(self.start, server, tool, arguments)
        except Exception:
            raise MCPAuditUnavailable("MCP read audit unavailable") from None
        started = time.perf_counter()
        status, result = "exception", None
        try:
            result = await operation()
            data = getattr(result, "data", None)
            failed = bool(getattr(result, "isError", False)) or (
                isinstance(data, dict) and "error" in data
            )
            status = "tool_error" if failed else "completed"
            return result
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        finally:
            try:
                await asyncio.shield(
                    asyncio.to_thread(
                        self.finish,
                        identity,
                        status,
                        result,
                        time.perf_counter() - started,
                    )
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                raise MCPAuditUnavailable("MCP read audit unavailable") from None


def audit_read(owner, tenant, server, run_id=None):
    """Wrap registered server reads; preserve the original public tool schema."""

    def decorate(function):
        signature = inspect.signature(function)

        @wraps(function)
        async def wrapped(*args, **kwargs):
            arguments = signature.bind(*args, **kwargs).arguments
            auditor = ReadAuditor(owner().engine, tenant, run_id)
            return await auditor.invoke(
                server, function.__name__, arguments, lambda: function(*args, **kwargs)
            )

        return wrapped

    return decorate
