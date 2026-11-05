"""Real edit/audit records and LangGraph store promotion. Provider events are fixtures."""

from contextlib import contextmanager
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from agent.handoffs import ProposalDraft, WritePreview
from agent.memory.service import MemoryService, MemoryUnavailable
from agent.memory.store import memory_namespace
from agent.proposal_nodes import draft_digest
from agent.run_store import RunConflict, RunNotFound
from apps.api.models import JobRecord, LocalDraftArtifact
from apps.api.schemas.memory import MemoryValue
from apps.api.schemas.proposals import ManualJob, ReviewRun
from tests.integration.test_runs import register


@pytest.fixture
def memories(client, account_app):
    user = register(client, "memory-fixture@example.org")
    return user, account_app.state.memory, account_app.state.runs


def edit_draft(store, tenant, *, unique="", before=None, after="Could we discuss scope?"):
    job = store.create_job(
        tenant,
        ManualJob(
            title=f"Python API {unique}",
            description="Build an API",
            billing_type="hourly",
            budget_max=30,
        ),
    )
    run = store.create_run(tenant, job.id, str(uuid4()))
    token = "memory-fixture-worker"
    store.claim(tenant, run.id, token)
    draft = ProposalDraft(text=before or "I am passionate about this work. Could we discuss scope?")
    preview = WritePreview(
        tool="save_local_draft",
        arguments={"draft_digest": draft_digest(draft)},
        connects_cost=0,
        idempotency_key=f"fixture:{run.id}",
    )
    store.save(
        tenant,
        run.id,
        token,
        {"draft": draft, "preview": preview},
        {
            "draft": draft.model_dump(),
            "preview": preview.model_dump(),
            "interrupt_id": f"fixture:{uuid4()}",
        },
        complete=True,
    )
    current = store.run(tenant, run.id)
    store.review(
        tenant,
        ReviewRun(
            run_id=run.id,
            version=current.version,
            draft_digest=draft_digest(draft),
            action="edit",
            edited_text=after,
        ),
    )
    return run


def seed_edits(store, tenant, count=3):
    return [edit_draft(store, tenant, unique=str(i)) for i in range(count)]


def test_edits_are_diffed_but_never_automatically_promoted(memories):
    user, memory, store = memories
    seed_edits(store, user["id"])
    edits = memory.edits(user["id"])
    assert len(edits) == 3 and "--- reviewed" in edits[0].diff
    assert "-I am passionate" in edits[0].diff and "+Could we discuss scope?" in edits[0].diff
    candidate = next(
        item for item in memory.candidates(user["id"]) if item.key == "avoid_passionate"
    )
    assert candidate.eligible and candidate.observations == 3 and not candidate.active
    assert memory.list(user["id"]).items == []
    with pytest.raises(RunConflict):
        memory.confirm_style(user["id"], "avoid_passionate", confirmed=False)


def test_confirmation_persists_only_derived_style_and_is_tenant_scoped(
    client, account_app, memories
):
    user, memory, store = memories
    runs = seed_edits(store, user["id"])
    result = memory.confirm_style(user["id"], "avoid_passionate", confirmed=True)
    assert not result.sync_pending and len(result.items) == 1
    entry = result.items[0]
    assert entry.value.observations == 3
    assert set(entry.value.supporting_run_ids) == {run.id for run in runs}
    assert "before_text" not in entry.value.model_dump()
    with memory.factory.open() as graph_store:
        item = graph_store.get(memory_namespace(user["id"], "style"), "avoid_passionate")
        assert MemoryValue.model_validate(item.value) == entry.value
        assert graph_store.search(memory_namespace(user["id"], "outcome")) == []
    # A new service instance against the same DB can recover the stored preference.
    restarted = MemoryService(memory.engine, account_app.state.settings.database_url)
    restarted.ensure()
    assert restarted.context(user["id"])["style_preferences"] == [entry.value.instruction]
    foreign = register(client, "foreign-memory@example.org")
    assert restarted.context(foreign["id"])["style_preferences"] == []
    assert memory.edits(foreign["id"]) == []
    with pytest.raises(RunNotFound):
        memory.remove(foreign["id"], "style", "avoid_passionate", entry.version)


def test_less_than_three_distinct_drafts_cannot_be_promoted(memories):
    user, memory, store = memories
    seed_edits(store, user["id"], count=2)
    with pytest.raises(RunConflict, match="three distinct drafts"):
        memory.confirm_style(user["id"], "avoid_passionate", confirmed=True)


class Unavailable:
    @contextmanager
    def open(self):
        raise ConnectionError("Development mirror outage")
        yield


def test_removal_survives_store_outage_and_stale_version_is_rejected(memories):
    user, memory, store = memories
    seed_edits(store, user["id"])
    entry = memory.confirm_style(user["id"], "avoid_passionate", confirmed=True).items[0]
    with pytest.raises(RunConflict):
        memory.remove(user["id"], "style", entry.key, entry.version + 1)
    actual = memory.factory
    memory.factory = Unavailable()
    try:
        with pytest.raises(MemoryUnavailable):
            memory.context(user["id"])
        # Removal is durable even while its LangGraph mirror cannot be reached.
        memory.remove(user["id"], "style", entry.key, entry.version)
        assert memory.list(user["id"]).items == []
    finally:
        memory.factory = actual
    assert memory.context(user["id"])["style_preferences"] == []
    with memory.factory.open() as graph_store:
        assert graph_store.get(memory_namespace(user["id"], "style"), entry.key) is None


def provider_run(store, tenant, name):
    job = store.create_job(
        tenant,
        ManualJob(
            title=name,
            description="Provider development fixture",
            billing_type="hourly",
            budget_max=30,
        ),
    )
    # Trusted adapter fixture only. No HTTP route can change a manual job's source.
    with Session(store.engine) as db, db.begin():
        row = db.get(JobRecord, job.id)
        row.raw = {**row.raw, "source": "gigsim"}
    run = store.create_run(tenant, job.id, str(uuid4()))
    with Session(store.engine) as db, db.begin():
        db.add(
            LocalDraftArtifact(
                run_id=run.id,
                user_id=tenant,
                draft={"text": "Could we discuss scope?", "claims": []},
                idempotency_key=f"provider-fixture:{run.id}",
            )
        )
    return run


def test_verified_outcomes_need_three_distinct_jobs_and_deduplicate_events(memories):
    user, memory, store = memories
    tenant = user["id"]
    runs = [provider_run(store, tenant, f"Provider job {i}") for i in range(3)]
    for i, run in enumerate(runs[:2]):
        memory.record_outcome(
            tenant, event_id=f"event:{i}", run_id=run.id, category="full_stack", outcome="replied"
        )
    assert memory.list(tenant).items == []
    # Multiple replies on one job are still one job, not repeated support.
    memory.record_outcome(
        tenant,
        event_id="event:duplicate-job",
        run_id=runs[0].id,
        category="full_stack",
        outcome="replied",
    )
    assert memory.list(tenant).items == []
    memory.record_outcome(
        tenant, event_id="event:2", run_id=runs[2].id, category="full_stack", outcome="replied"
    )
    memory.record_outcome(
        tenant, event_id="event:2", run_id=runs[2].id, category="full_stack", outcome="replied"
    )
    result = memory.list(tenant)
    assert not result.sync_pending and len(result.items) == 1
    entry = result.items[0]
    assert entry.kind == "outcome" and entry.value.observations == 3
    assert entry.value.proposal_features.artifact_samples == 3
    assert entry.value.proposal_features.mean_cover_words == 4
    assert entry.value.proposal_features.question_fraction == 1
    with pytest.raises(RunConflict, match="conflicting"):
        memory.record_outcome(
            tenant, event_id="event:2", run_id=runs[2].id, category="full_stack", outcome="won"
        )
    memory.remove(tenant, "outcome", entry.key, entry.version)
    memory.record_outcome(
        tenant,
        event_id="event:after-remove",
        run_id=runs[2].id,
        category="full_stack",
        outcome="replied",
    )
    assert memory.list(tenant).items == []  # Automatic updates cannot resurrect removal.


def test_manual_jobs_cannot_manufacture_outcome_memory(memories):
    user, memory, store = memories
    run = seed_edits(store, user["id"], count=1)[0]
    with pytest.raises(RunConflict, match="manual job"):
        memory.record_outcome(
            user["id"], event_id="fake-win", run_id=run.id, category="ai_ml", outcome="won"
        )


def test_memory_api_confirmation_csrf_and_private_diff_history(client, memories):
    user, memory, store = memories
    seed_edits(store, user["id"])
    body = {"key": "avoid_passionate", "confirmed": True}
    assert client.post("/api/memory/style", json=body).status_code == 403
    headers = {"X-CSRF-Token": user["csrf_token"]}
    response = client.post("/api/memory/style", json=body, headers=headers)
    assert response.status_code == 200, response.text
    entry = response.json()["items"][0]
    assert len(client.get("/api/memory/edits").json()) == 3
    assert client.post(
        "/api/memory/outcome", json={"outcome": "won"}, headers=headers
    ).status_code in {404, 405}
    response = client.request(
        "DELETE",
        "/api/memory/style/avoid_passionate",
        json={"version": entry["version"]},
        headers=headers,
    )
    assert response.status_code == 204
    assert client.get("/api/memory").json()["items"] == []
