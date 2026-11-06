"""Local Workspace MCP, exact approval binding, tenant boundaries and concurrent holds."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agent.handoffs import ProposalDraft, WritePreview
from agent.proposal_nodes import draft_digest
from agent.run_store import RunConflict
from apps.api.models import AgentRun, CalendarHold, WorkspaceWrite
from apps.api.schemas.proposals import ManualJob, ReviewRun
from mcp_servers.workspace.factory import create_workspace_server
from mcp_servers.workspace.service import WorkspaceService
from mcp_servers.workspace.tools import EmailDraftRequest, HoldRequest, SlotRequest
from tests.integration.test_runs import register

NOW = datetime(2030, 1, 1, 9, 0, 0, 100, tzinfo=UTC)


@pytest.fixture
def workspace(client, account_app):
    user = register(client, "workspace@example.org")
    service = WorkspaceService(account_app.state.engine, clock=lambda: NOW)
    service.add_availability(user["id"], NOW.replace(microsecond=0), NOW + timedelta(hours=3))
    return user, service, account_app.state.runs


def approve(store, tenant, tool, arguments, key, *, action="approve"):
    job = store.create_job(
        tenant,
        ManualJob(
            title="Workspace approval fixture",
            description="Development action",
            billing_type="hourly",
            budget_max=30,
        ),
    )
    run = store.create_run(tenant, job.id, str(uuid4()))
    token = "workspace-fixture-worker"
    store.claim(tenant, run.id, token)
    draft = ProposalDraft(text=arguments.get("body", "Could we discuss the project?"))
    preview = WritePreview(tool=tool, arguments=arguments, connects_cost=0, idempotency_key=key)
    store.save(
        tenant,
        run.id,
        token,
        {"draft": draft, "preview": preview},
        {
            "draft": draft.model_dump(),
            "preview": preview.model_dump(),
            "interrupt_id": str(uuid4()),
        },
        complete=True,
    )
    view = store.run(tenant, run.id)
    store.review(
        tenant,
        ReviewRun(
            run_id=run.id,
            version=view.version,
            draft_digest=draft_digest(draft),
            action=action,
            reason="Development rejection" if action == "reject" else None,
        ),
    )
    return run.id


def test_free_slots_respect_fractional_start_timezone_holds_and_account(workspace):
    user, service, store = workspace
    tenant = user["id"]
    query = SlotRequest(start=NOW, end=NOW + timedelta(hours=2))
    initial = service.free_slots(tenant, query)["slots"]
    assert initial[0]["start"] == "2030-01-01T09:15:00+00:00"
    assert service.free_slots("another-user", query)["slots"] == []
    request = HoldRequest(start=initial[0]["start"], minutes=30, idempotency_key="hold-fixture-1")
    preview = service.hold(tenant, None, request)
    run = approve(
        store, tenant, "create_interview_hold", preview["arguments"], request.idempotency_key
    )
    saved = service.hold(tenant, run, request.model_copy(update={"dry_run": False}))
    assert saved["status"] == "tentative"
    remaining = service.free_slots(tenant, query)["slots"]
    assert remaining[0]["start"] == "2030-01-01T09:45:00+00:00"


def test_dry_run_is_side_effect_free_and_write_requires_exact_preview(workspace):
    user, service, store = workspace
    request = EmailDraftRequest(
        subject="Project follow-up",
        body="Could we discuss scope?",
        idempotency_key="email-fixture-1",
    )
    preview = service.email(user["id"], None, request)
    assert preview["dry_run"] and service.actions(user["id"]) == []
    run = approve(
        store, user["id"], "create_email_draft", preview["arguments"], request.idempotency_key
    )
    with pytest.raises(RunConflict, match="exact preview"):
        service.email(
            user["id"], run, request.model_copy(update={"body": "Changed", "dry_run": False})
        )
    with pytest.raises(RunConflict, match="exact preview"):
        service.email(
            user["id"],
            run,
            request.model_copy(update={"idempotency_key": "different-key", "dry_run": False}),
        )
    saved = service.email(user["id"], run, request.model_copy(update={"dry_run": False}))
    assert saved["status"] == "draft"
    assert service.email(user["id"], run, request.model_copy(update={"dry_run": False})) == saved
    assert len(service.actions(user["id"])) == 1
    assert service.actions("another-user") == []


def test_rejected_action_and_stale_calendar_slot_cannot_execute(workspace):
    user, service, store = workspace
    request = HoldRequest(
        start=NOW + timedelta(hours=1), minutes=30, idempotency_key="stale-slot-fixture"
    )
    preview = service.hold(user["id"], None, request)
    rejected = approve(
        store,
        user["id"],
        "create_interview_hold",
        preview["arguments"],
        request.idempotency_key,
        action="reject",
    )
    with pytest.raises(RunConflict, match="approval"):
        service.hold(user["id"], rejected, request.model_copy(update={"dry_run": False}))
    accepted = approve(
        store, user["id"], "create_interview_hold", preview["arguments"], request.idempotency_key
    )
    for window in service.availability(user["id"]):
        service.remove_availability(user["id"], window["id"])
    with pytest.raises(RunConflict, match="no longer available"):
        service.hold(user["id"], accepted, request.model_copy(update={"dry_run": False}))


def test_changed_run_preview_invalidates_an_old_approval(workspace):
    user, service, store = workspace
    request = EmailDraftRequest(
        subject="Review fixture",
        body="Could we discuss scope?",
        idempotency_key="changed-preview-fixture",
    )
    preview = service.email(user["id"], None, request)
    run_id = approve(
        store, user["id"], "create_email_draft", preview["arguments"], request.idempotency_key
    )
    with Session(service.engine) as db, db.begin():
        run = db.get(AgentRun, run_id)
        run.snapshot = {**run.snapshot, "preview": None}
    with pytest.raises(RunConflict, match="exact preview"):
        service.email(user["id"], run_id, request.model_copy(update={"dry_run": False}))
    assert service.actions(user["id"]) == []


def test_concurrent_holds_share_user_lock_and_only_one_can_book(workspace):
    user, service, store = workspace
    if service.engine.dialect.name != "postgresql":
        pytest.skip("Requires actual Postgres row locks")
    requests = [
        HoldRequest(
            start=NOW + timedelta(hours=1), minutes=30, idempotency_key=f"concurrent-fixture-{i}"
        )
        for i in range(2)
    ]
    runs = [
        approve(
            store,
            user["id"],
            "create_interview_hold",
            service.hold(user["id"], None, request)["arguments"],
            request.idempotency_key,
        )
        for request in requests
    ]

    def attempt(index):
        try:
            service.hold(
                user["id"], runs[index], requests[index].model_copy(update={"dry_run": False})
            )
            return "held"
        except RunConflict:
            return "occupied"

    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(attempt, range(2))) == ["held", "occupied"]
    with Session(service.engine) as db:
        assert db.scalar(select(func.count()).select_from(CalendarHold)) == 1
        assert db.scalar(select(func.count()).select_from(WorkspaceWrite)) == 1


async def test_actual_mcp_session_exposes_local_tools_and_binds_run(workspace):
    user, service, store = workspace
    request = EmailDraftRequest(
        subject="MCP fixture", body="Could we discuss scope?", idempotency_key="mcp-email-fixture"
    )
    preview = service.email(user["id"], None, request)
    run = approve(
        store, user["id"], "create_email_draft", preview["arguments"], request.idempotency_key
    )
    server = create_workspace_server(service, user["id"], run)
    async with create_connected_server_and_client_session(server) as client:
        tools = await client.list_tools()
        assert all(tool.annotations.idempotentHint for tool in tools.tools)
        result = await client.call_tool(
            "create_email_draft",
            {
                "request": {
                    **request.model_dump(mode="json"),
                    "dry_run": False,
                }
            },
        )
        assert not result.isError and result.structuredContent["data"]["status"] == "draft"
    foreign = create_workspace_server(service, "another-user", run)
    async with create_connected_server_and_client_session(foreign) as client:
        result = await client.call_tool(
            "create_email_draft",
            {
                "request": {
                    **request.model_dump(mode="json"),
                    "dry_run": False,
                }
            },
        )
        assert result.isError


def test_availability_api_rejects_naive_timestamps_and_enforces_csrf(client, account_app):
    user = register(client, "availability-api@example.org")
    account_app.state.workspace = WorkspaceService(account_app.state.engine, clock=lambda: NOW)
    headers = {"X-CSRF-Token": user["csrf_token"]}
    body = {"start": "2030-01-01T14:00:00+05:00", "end": "2030-01-01T16:00:00+05:00"}
    assert client.post("/api/workspace/availability", json=body).status_code == 403
    assert (
        client.post(
            "/api/workspace/availability",
            json={
                "start": "2030-01-01T09:00:00",
                "end": "2030-01-01T10:00:00",
            },
            headers=headers,
        ).status_code
        == 422
    )
    response = client.post("/api/workspace/availability", json=body, headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()["start"].startswith("2030-01-01T09:00:00")
    assert (
        client.delete(
            f"/api/workspace/availability/{response.json()['id']}", headers=headers
        ).status_code
        == 204
    )
