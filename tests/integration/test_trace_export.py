from uuid import UUID

import pytest

from agent.run_store import RunNotFound
from agent.tracing import export_run
from tests.integration.test_runs import register
from tests.integration.test_runs import run_fixture as run_fixture


def test_trace_export_is_tenant_scoped_idempotent_and_retryable(account_app, run_fixture):
    user, store, run, *_ = run_fixture
    settings = account_app.state.settings.model_copy(update={"trace_export_enabled": True})
    calls = []

    class Client:
        fail = True

        def batch_ingest_runs(self, **kwargs):
            if self.fail:
                raise ConnectionError("Synthetic provider outage")
            calls.append(kwargs)

    client = Client()
    with pytest.raises(RunNotFound):
        export_run(store.engine, settings, "other-account", run.id, client=client)
    with pytest.raises(ConnectionError):
        export_run(store.engine, settings, user["id"], run.id, client=client)
    assert not any(e.kind == "trace_exported" for e in store.events(user["id"], run.id))
    client.fail = False
    first = export_run(store.engine, settings, user["id"], run.id, client=client)
    assert first == export_run(store.engine, settings, user["id"], run.id, client=client)
    assert len(calls) == 1
    assert not calls[0]["update"]
    assert calls[0]["create"][0]["id"] == first["remote_trace_id"]
    assert calls[0]["create"][0]["extra"]["metadata"]["trace_id"] == run.id

    # Real SDK normalizes IDs in place. Snapshots must survive mutation without
    # a failed local audit commit, and never patch already closed remote spans.
    class MutatingClient:
        def batch_ingest_runs(self, *, create, update):
            assert not update
            for span in create:
                span["id"] = UUID(str(span["id"]))

    from sqlalchemy.orm import Session

    from apps.api.models import RunEvent

    with Session(store.engine) as db, db.begin():
        db.add(RunEvent(run_id=run.id, kind="recovery_observed", details={}))
    result = export_run(store.engine, settings, user["id"], run.id, client=MutatingClient())
    assert result["remote_trace_id"] != first["remote_trace_id"]
    assert all(isinstance(identity, str) for identity in result["span_ids"])
    assert export_run(store.engine, settings, user["id"], run.id, client=MutatingClient()) == result


def test_trace_endpoint_cannot_read_another_users_run(client, run_fixture):
    user, _, run, *_ = run_fixture
    response = client.get(f"/api/runs/{run.id}/trace")
    assert response.status_code == 200 and response.json()["trace_id"] == run.id
    client.post("/api/auth/logout", headers={"X-CSRF-Token": user["csrf_token"]})
    register(client, "trace-other@example.org")
    assert client.get(f"/api/runs/{run.id}/trace").status_code == 404
