"""Opt-in regression for Windows stdio/native-library startup and real retrieval."""

import os
import sys

import pytest

from agent.mcp_client import build_client
from agent.portfolio_client import PortfolioMCP
from apps.api.settings import Settings
from rag.contracts import DocumentMetadata
from rag.runtime import build_portfolio


@pytest.mark.skipif(
    os.getenv("GIGBID_REAL_MODELS") != "1", reason="requires local models and Qdrant"
)
@pytest.mark.asyncio
async def test_standalone_portfolio_mcp_retrieves_real_indexed_evidence(client, account_app):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "stdio-smoke@example.org",
            "password": "Stdio regression fixture password 123!",
        },
    )
    assert response.status_code == 201
    user = response.json()["id"]
    settings = Settings()
    service = build_portfolio(account_app.state.engine, settings)
    doc = service.ingest(
        user,
        "stdio-development-fixture.md",
        b"Built a Python FastAPI service.",
        DocumentMetadata(type="case_study", project="Stdio development fixture"),
    )
    service.index_document(user, doc.id)
    try:
        mcp = build_client(
            {
                "portfolio": {
                    "transport": "stdio",
                    "command": sys.executable,
                    "args": ["-m", "mcp_servers.portfolio.server"],
                    "env": {
                        "GIGBID_TENANT_ID": user,
                        "DATABASE_URL": account_app.state.settings.database_url,
                        "MODEL_CACHE_DIR": str(settings.model_cache_dir),
                    },
                }
            }
        )
        async with mcp.session("portfolio") as session:
            result = await session.call_tool(
                "search_evidence", {"request": {"requirement": "Python API"}}
            )
            assert not result.isError
            assert result.structuredContent["items"][0]["document_id"] == doc.id
            item = result.structuredContent["items"][0]
            assert (await PortfolioMCP(session).read(item["id"])).id == item["id"]
    finally:
        service.delete_document(user, doc.id)
        service.cleanup_vectors(user, doc.id)
        service.index.client.close()
