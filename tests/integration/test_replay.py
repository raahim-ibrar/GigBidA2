"""Real checkpoint replay forks never inherit a send approval or overwrite history."""

from uuid import uuid4

import pytest

from agent.replay import checkpoints, effective_node, fork
from agent.run_store import RunConflict, RunNotFound
from apps.api.schemas.proposals import ReplayRun, ReviewRun
from tests.integration.test_durable_bid import durable as durable
from tests.integration.test_durable_bid import execute


def test_fork_from_writer_reuses_typed_state_and_requires_new_approval(durable):
    store, tenant, parent, process, _, _, counts, settings = durable
    assert execute(process())["status"] == "awaiting_approval"
    history = execute(checkpoints(store.engine, settings, tenant, parent))
    source = next(c for c in history if c["next_nodes"] == ["writer"])
    body = ReplayRun(checkpoint_id=source["checkpoint_id"], node="writer")
    replay = execute(fork(store.engine, settings, store, tenant, parent, body))
    assert execute(fork(store.engine, settings, store, tenant, parent, body)).id == replay.id
    assert replay.id != parent and replay.status == "queued"
    assert execute(process(replay.id))["status"] == "awaiting_approval"
    assert counts["analyst"] == 1 and counts["writer"] == 2
    current = store.run(tenant, replay.id)
    assert replay.id in current.review["preview"]["idempotency_key"]
    assert store.run(tenant, parent).status == "awaiting_approval"
    store.review(
        tenant,
        ReviewRun(
            run_id=replay.id,
            version=current.version,
            action="approve",
            draft_digest=current.review["preview"]["arguments"]["draft_digest"],
        ),
    )
    assert execute(process(replay.id))["status"] == "drafted"
    assert store.run(tenant, parent).status == "awaiting_approval"


def test_execution_replay_reverifies_and_cannot_inherit_approval(durable):
    store, tenant, parent, process, _, _, counts, settings = durable
    execute(process())
    approved = store.run(tenant, parent)
    store.review(
        tenant,
        ReviewRun(
            run_id=parent,
            version=approved.version,
            action="approve",
            draft_digest=approved.review["preview"]["arguments"]["draft_digest"],
        ),
    )
    assert execute(process())["status"] == "drafted"
    history = execute(checkpoints(store.engine, settings, tenant, parent))
    body = ReplayRun(checkpoint_id=history[0]["checkpoint_id"], node="execute")
    replay = execute(fork(store.engine, settings, store, tenant, parent, body))
    assert replay.snapshot.replay_request["effective_node"] == "verifier"
    assert execute(process(replay.id))["status"] == "awaiting_approval"
    assert counts["verifier"] == 2
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    from apps.api.models import LocalDraftArtifact

    with Session(store.engine) as db:
        assert db.scalar(select(func.count()).select_from(LocalDraftArtifact)) == 1


def test_checkpoint_owner_and_missing_id_are_enforced(durable):
    store, tenant, parent, process, *_, settings = durable
    execute(process())
    with pytest.raises(RunNotFound):
        execute(checkpoints(store.engine, settings, "other-user", parent))
    with pytest.raises(RunNotFound):
        execute(checkpoints(store.engine, settings, tenant, parent, str(uuid4())))
    with pytest.raises(RunConflict):
        effective_node("unregistered_tool")


def test_replay_routes_require_owner_session_csrf_and_new_approval(durable, client, account_app):
    store, tenant, parent, process, *_, settings = durable
    execute(process())
    history = client.get(f"/api/runs/{parent}/checkpoints")
    assert history.status_code == 200, history.text
    body = {"checkpoint_id": history.json()[0]["checkpoint_id"], "node": "execute"}
    assert client.post(f"/api/runs/{parent}/replays", json=body).status_code == 403
    me = client.get("/api/auth/me").json()

    async def queued(*args):
        return True

    account_app.state.enqueue_run = queued
    response = client.post(
        f"/api/runs/{parent}/replays",
        json=body,
        headers={"X-CSRF-Token": me["csrf_token"]},
    )
    assert response.status_code == 202, response.text
    assert response.json()["id"] != parent
    assert response.json()["status"] == "queued"
    client.post("/api/auth/logout", headers={"X-CSRF-Token": me["csrf_token"]})
    assert client.get(f"/api/runs/{parent}/checkpoints").status_code == 401
    from tests.integration.test_runs import register

    other = register(client, "other-replay-owner@example.org")
    assert client.get(f"/api/runs/{parent}/checkpoints").status_code == 404
    assert (
        client.post(
            f"/api/runs/{parent}/replays",
            json=body,
            headers={"X-CSRF-Token": other["csrf_token"]},
        ).status_code
        == 404
    )
