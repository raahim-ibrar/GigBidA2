import asyncio
from uuid import uuid4

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CallToolResult, TextContent
from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.mcp_audit import MCPAuditUnavailable, ReadAuditor
from agent.run_store import RunStore
from apps.api.models import MCPReadAudit
from apps.api.schemas.proposals import ManualJob
from mcp_servers.portfolio.factory import create_portfolio_server
from rag.contracts import DocumentMetadata
from tests.integration.test_runs import register
from tests.portfolio_fixtures import portfolio_fixture


@pytest.fixture
def audit_owner(client, account_app):
    user = register(client, "audit-owner@example.org")
    return user, ReadAuditor(account_app.state.engine, user["id"])


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["completed", "tool_error", "exception", "cancelled"])
async def test_durable_attempt_result_and_failure_are_redacted(audit_owner, account_app, outcome):
    user, auditor = audit_owner

    async def operation():
        with Session(account_app.state.engine) as db:
            assert db.scalar(select(MCPReadAudit)).status == "started"
        if outcome == "exception":
            raise RuntimeError("SECRET_EXCEPTION_CV")
        if outcome == "cancelled":
            raise asyncio.CancelledError("SECRET_EXCEPTION_CV")
        return CallToolResult(
            content=[TextContent(type="text", text="PRIVATE_RESULT")],
            structuredContent={"count": 7, "api_key": "SECRET_RESULT"},
            isError=outcome == "tool_error",
        )

    if outcome in {"exception", "cancelled"}:
        with pytest.raises(RuntimeError if outcome == "exception" else asyncio.CancelledError):
            await auditor.invoke(
                "portfolio", "search_evidence", {"query": "PRIVATE_QUERY"}, operation
            )
    else:
        actual = await auditor.invoke(
            "portfolio", "search_evidence", {"query": "PRIVATE_QUERY"}, operation
        )
        assert (
            actual.structuredContent["api_key"] == "SECRET_RESULT"
        )  # Inference still gets original.
    with Session(account_app.state.engine) as db:
        row = db.scalar(select(MCPReadAudit))
        assert row.status == outcome and row.user_id == user["id"]
        assert row.finished_at and row.elapsed_seconds >= 0
        assert "PRIVATE" not in repr(row.arguments) + repr(row.result)
        assert "SECRET" not in repr(row.arguments) + repr(row.result)


@pytest.mark.asyncio
async def test_audit_failure_blocks_dispatch_or_return(audit_owner, monkeypatch):
    _, auditor = audit_owner
    calls = []

    async def operation():
        calls.append(True)
        return {"text": "PRIVATE_RESULT"}

    def fail(*args):
        raise RuntimeError("SECRET_DATABASE_DETAILS")

    with monkeypatch.context() as patch:
        patch.setattr(auditor, "start", fail)
        with pytest.raises(MCPAuditUnavailable, match="audit unavailable"):
            await auditor.invoke("portfolio", "list_skills", {}, operation)
    assert not calls
    monkeypatch.setattr(auditor, "finish", fail)
    with pytest.raises(MCPAuditUnavailable, match="audit unavailable"):
        await auditor.invoke("portfolio", "list_skills", {}, operation)
    assert calls == [True]


def test_owner_api_pagination_run_binding_and_interrupted_attempt(audit_owner, account_app, client):
    user, auditor = audit_owner
    store = RunStore(account_app.state.engine)
    job = store.create_job(
        user["id"],
        ManualJob(title="Fixture", description="Fixture", billing_type="fixed", budget_max=100),
    )
    run = store.create_run(user["id"], job.id, str(uuid4()))
    bound = ReadAuditor(account_app.state.engine, user["id"], run.id)
    bound.start("portfolio", "list_skills", {})  # A crash leaves a durable started receipt.
    auditor.start("portfolio", "list_skills", {})
    rows = client.get("/api/mcp/read-audits", params={"run_id": run.id}).json()
    assert len(rows) == 1 and rows[0]["status"] == "started" and rows[0]["finished_at"] is None
    assert len(client.get("/api/mcp/read-audits?limit=1&offset=1").json()) == 1
    assert client.get("/api/mcp/read-audits?limit=201").status_code == 422
    client.post("/api/auth/logout", headers={"X-CSRF-Token": user["csrf_token"]})
    assert client.get("/api/mcp/read-audits").status_code == 401
    other = register(client, "audit-other@example.org")
    assert client.get("/api/mcp/read-audits").json() == []
    assert client.get("/api/mcp/read-audits", params={"run_id": run.id}).status_code == 404
    with pytest.raises(Exception, match="run not found"):
        ReadAuditor(account_app.state.engine, other["id"], run.id).start(
            "portfolio", "list_skills", {}
        )


@pytest.mark.asyncio
async def test_actual_mcp_reads_are_audited_outside_graph(audit_owner, account_app):
    user, _ = audit_owner
    service = portfolio_fixture(account_app.state.engine)
    doc = service.ingest(
        user["id"],
        "private.md",
        b"PRIVATE_CV Python API",
        DocumentMetadata(type="case_study", project="PRIVATE_PROJECT"),
    )
    service.index_document(user["id"], doc.id)
    server = create_portfolio_server(service, user["id"])
    async with create_connected_server_and_client_session(server) as session:
        assert not (await session.call_tool("list_skills", {})).isError
        assert not (await session.call_tool("get_case_study", {"id": doc.id})).isError
        assert not (
            await session.call_tool(
                "search_evidence", {"request": {"requirement": "PRIVATE_QUERY Python"}}
            )
        ).isError
        assert (await session.call_tool("get_case_study", {"id": str(uuid4())})).isError
    with Session(account_app.state.engine) as db:
        rows = list(db.scalars(select(MCPReadAudit)))
        assert len(rows) == 4 and sum(r.status == "exception" for r in rows) == 1
        assert all(r.run_id is None for r in rows)
        assert "PRIVATE" not in repr([(r.arguments, r.result) for r in rows])
