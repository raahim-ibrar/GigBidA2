"""Check the assignment's fixed paths. Existence does not imply feature completion."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "README.md",
    "Makefile",
    "pyproject.toml",
    ".env.example",
    "apps/web/src/app",
    "apps/web/src/components",
    "apps/web/src/lib/api",
    "apps/web/tests/e2e",
    "apps/api/main.py",
    "apps/api/routers",
    "apps/api/streaming.py",
    "apps/api/auth",
    "apps/api/schemas",
    "agent/state.py",
    "agent/handoffs.py",
    "agent/graphs/bid_graph.py",
    "agent/graphs/conversation_graph.py",
    "agent/nodes",
    "agent/prompts",
    "agent/memory",
    "agent/mcp_client.py",
    "agent/marketplace_port.py",
    "agent/config.yaml",
    "rag/ingest",
    "rag/index",
    "rag/variants",
    "rag/retriever.py",
    "rag/verify.py",
    "mcp_servers/portfolio",
    "mcp_servers/marketplace/adapters/gigsim.py",
    "mcp_servers/marketplace/adapters/upwork_live.py",
    "mcp_servers/workspace",
    "worker",
    "gigsim",
    "data/personas",
    "data/policy_pack",
    "data/processed",
    "evals/datasets",
    "evals/runners",
    "evals/results",
    "tests/unit",
    "tests/integration",
    "tests/contract",
    "infra/docker",
    "infra/docker-compose.yml",
    ".github/workflows/ci.yml",
    ".github/workflows/eval.yml",
    "docs/ARCHITECTURE.md",
    "docs/adr",
    "docs/DATA_CARD.md",
    "docs/TOOLS.md",
    "docs/RUNBOOK.md",
    "docs/EXTENSION.md",
    "docs/AI_USAGE.md",
    "docs/images",
)


def check():
    missing = [path for path in REQUIRED if not (ROOT / path).exists()]
    if missing:
        raise SystemExit("Missing required paths: " + ", ".join(missing))
    print(f"All {len(REQUIRED)} required scaffold paths exist.")


if __name__ == "__main__":
    check()
