import json

import pytest
from fastapi.testclient import TestClient
from mcp.shared.memory import create_connected_server_and_client_session
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.models import EvidenceChunk, VectorCleanup
from mcp_servers.portfolio.factory import create_portfolio_server
from rag.contracts import DocumentMetadata, PortfolioSearch
from tests.portfolio_fixtures import portfolio_fixture

METADATA = {
    "type": "case_study",
    "project": "Service API",
    "skills": ["Python", "FastAPI"],
    "persona": "own",
}
SOURCE = b"Built a Python FastAPI service with PostgreSQL for a retail client."


@pytest.fixture
def portfolio(account_app):
    service = portfolio_fixture(account_app.state.engine)
    account_app.state.portfolio = service

    async def enqueue(tenant, document, revision):
        service.index_document(tenant, document)
        return True

    account_app.state.enqueue_portfolio = enqueue
    yield service
    service.index.client.close()


def account(client, email="portfolio@example.org"):
    response = client.post(
        "/api/auth/register", json={"email": email, "password": "Portfolio test password 123!"}
    )
    assert response.status_code == 201
    return response.json()


def upload(client, user, content=SOURCE, filename="case.md", metadata=METADATA):
    return client.post(
        "/api/portfolio/documents",
        files={"file": (filename, content, "text/markdown")},
        data={"metadata": json.dumps(metadata)},
        headers={"X-CSRF-Token": user["csrf_token"]},
    )


def test_upload_index_search_and_metadata(client, portfolio):
    user = account(client)
    created = upload(client, user)
    assert created.status_code == 201, created.text
    documents = client.get("/api/portfolio/documents").json()
    assert documents[0]["status"] == "ready"
    result = client.post(
        "/api/portfolio/search",
        json={"query": "Python API", "variant": "v2"},
        headers={"X-CSRF-Token": user["csrf_token"]},
    )
    assert result.status_code == 200, result.text
    item = result.json()["items"][0]["evidence"]
    assert item["text"] == SOURCE.decode()
    assert item["source"] == "case.md"
    assert item["document_id"] == created.json()["id"]
    assert item["skills"] == ["Python", "FastAPI"]


def test_same_source_is_idempotent_and_replacement_invalidates_old_evidence(client, portfolio):
    user = account(client)
    first = upload(client, user).json()
    old = portfolio.search(user["id"], PortfolioSearch(query="Python API")).items[0].evidence.id
    assert upload(client, user).json()["revision"] == 1
    replaced = upload(client, user, b"Created a brochure and a logo design.").json()
    assert replaced["id"] == first["id"] and replaced["revision"] == 2
    assert client.get(f"/api/portfolio/evidence/{old}").status_code == 404
    assert len(client.get("/api/portfolio/documents").json()) == 1


def test_two_accounts_cannot_read_search_replace_or_delete_each_others_sources(
    account_app, portfolio
):
    with TestClient(account_app) as alice, TestClient(account_app) as bob:
        a, b = account(alice, "a@example.org"), account(bob, "b@example.org")
        doc = upload(alice, a).json()
        evidence = (
            portfolio.search(a["id"], PortfolioSearch(query="Python API")).items[0].evidence.id
        )
        assert bob.get("/api/portfolio/documents").json() == []
        assert portfolio.search(b["id"], PortfolioSearch(query="Python API")).items == []
        assert bob.get(f"/api/portfolio/evidence/{evidence}").status_code == 404
        assert (
            bob.delete(
                f"/api/portfolio/documents/{doc['id']}", headers={"X-CSRF-Token": b["csrf_token"]}
            ).status_code
            == 404
        )
        assert upload(bob, b).json()["id"] != doc["id"]


def test_delete_removes_source_text_immediately_and_uses_durable_vector_cleanup(
    client, portfolio, account_app
):
    user = account(client)
    doc = upload(client, user).json()
    assert (
        client.delete(
            f"/api/portfolio/documents/{doc['id']}", headers={"X-CSRF-Token": user["csrf_token"]}
        ).status_code
        == 204
    )
    assert portfolio.search(user["id"], PortfolioSearch(query="Python API")).items == []
    with Session(account_app.state.engine) as db:
        assert db.scalar(select(EvidenceChunk).where(EvidenceChunk.user_id == user["id"])) is None
        assert db.get(VectorCleanup, doc["id"]) is not None
    portfolio.cleanup_vectors(user["id"], doc["id"])
    with Session(account_app.state.engine) as db:
        assert db.get(VectorCleanup, doc["id"]) is None


def test_missing_queue_preserves_a_pending_upload(client, portfolio, account_app):
    async def unavailable(*args):
        return False

    account_app.state.enqueue_portfolio = unavailable
    user = account(client)
    response = upload(client, user)
    assert response.status_code == 201 and response.json()["status"] == "queued"
    assert "queue unavailable" in response.json()["error"]
    assert client.get("/api/portfolio/documents").json()[0]["status"] == "queued"


def test_indexing_failure_is_visible_and_retrieval_does_not_use_failed_sources(client, portfolio):
    user = account(client)
    doc = portfolio.ingest(user["id"], "case.md", SOURCE, DocumentMetadata(**METADATA))
    portfolio.set_index_error(user["id"], doc.id)
    assert portfolio.list_documents(user["id"])[0].status == "failed"
    assert portfolio.search(user["id"], PortfolioSearch(query="Python API")).items == []
    assert portfolio.retry(user["id"], doc.id).status == "queued"


@pytest.mark.parametrize("variant", ["v0", "v1", "v2", "v3", "v8"])
def test_all_variants_execute_with_injected_test_models(client, portfolio, variant):
    user = account(client)
    upload(client, user)
    result = portfolio.search(user["id"], PortfolioSearch(query="Python", variant=variant))
    assert result.items and result.variant == variant
    assert result.queries


@pytest.mark.asyncio
async def test_real_portfolio_tools_work_through_mcp_and_remain_tenant_bound(client, portfolio):
    user = account(client)
    doc = upload(client, user).json()
    mcp = create_portfolio_server(portfolio, user["id"])
    async with create_connected_server_and_client_session(mcp) as session:
        result = await session.call_tool("search_evidence", {"request": {"requirement": "Python"}})
        assert not result.isError
        assert "FastAPI" in str(result.structuredContent)
        skills = await session.call_tool("list_skills", {})
        assert "Python" in str(skills.structuredContent)
        source = await session.call_tool("get_case_study", {"id": doc["id"]})
        assert not source.isError
    foreign = create_portfolio_server(portfolio, "a-different-tenant")
    async with create_connected_server_and_client_session(foreign) as session:
        result = await session.call_tool("get_case_study", {"id": doc["id"]})
        assert result.isError
