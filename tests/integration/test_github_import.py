from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from rag.contracts import DocumentMetadata
from rag.github_import import GitHubImport
from tests.integration.test_portfolio import account
from tests.integration.test_portfolio import portfolio as portfolio


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/a/b",
        "https://evil.test/a/b",
        "https://github.com/a/b?x=y",
        "https://github.com/a/b/../c",
    ],
)
def test_rejects_noncanonical_repository_url(url):
    with pytest.raises(ValidationError):
        GitHubImport(repository_url=url, project="Test")


def test_import_is_authenticated_csrf_scoped_and_indexed(account_app, portfolio, monkeypatch):
    async def fetch(body, settings):
        return (
            "github-a-b-README.md",
            b"Built a Python API for fictional coursework.",
            DocumentMetadata(
                project=body.project,
                type="readme",
                skills=["Python"],
                source_commit="a" * 40,
                source_url="https://github.com/a/b/blob/" + "a" * 40 + "/README.md",
            ),
        )

    monkeypatch.setattr("apps.api.routers.portfolio.fetch_readme", fetch)
    body = {"repository_url": "https://github.com/a/b", "project": "Test"}
    with TestClient(account_app) as client:
        assert client.post("/api/portfolio/import/github", json=body).status_code == 401
        user = account(client)
        assert client.post("/api/portfolio/import/github", json=body).status_code == 403
        headers = {"X-CSRF-Token": user["csrf_token"]}
        response = client.post("/api/portfolio/import/github", json=body, headers=headers)
        assert response.status_code == 201, response.text
        assert response.json()["details"]["source_commit"] == "a" * 40
        assert client.get("/api/portfolio/documents").json()[0]["status"] == "ready"
        first = response.json()["id"]
        assert (
            client.post("/api/portfolio/import/github", json=body, headers=headers).json()["id"]
            == first
        )
        client.post("/api/auth/logout", headers=headers)
        account(client, "other@example.org")
        assert client.get("/api/portfolio/documents").json() == []


@pytest.mark.asyncio
async def test_github_mcp_pins_commit_and_reads_embedded_resource(monkeypatch):
    from rag.github_import import fetch_readme

    calls = []

    class Remote:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def call_tool(self, name, arguments):
            calls.append((name, arguments))
            data = {
                "search_repositories": {"items": [{"full_name": "a/b", "private": False}]},
                "get_commit": {"sha": "a" * 40},
            }
            return SimpleNamespace(
                isError=False,
                structuredContent=data.get(name),
                content=[
                    SimpleNamespace(type="resource", resource=SimpleNamespace(text="Actual README"))
                ],
            )

    class Client:
        def session(self, name):
            return Remote()

    def build(config):
        assert config["github"]["url"] == "https://api.githubcopilot.com/mcp/"
        assert config["github"]["headers"]["X-MCP-Readonly"] == "true"
        return Client()

    monkeypatch.setattr("rag.github_import.build_client", build)
    settings = SimpleNamespace(
        github_token=SimpleNamespace(get_secret_value=lambda: "fake-test-key")
    )
    _, text, metadata = await fetch_readme(
        GitHubImport(repository_url="https://github.com/a/b.git", project="Test"), settings
    )
    assert b"Actual README" in text and metadata.source_commit == "a" * 40
    assert calls[-1][1]["sha"] == "a" * 40
