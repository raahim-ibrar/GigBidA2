from typing import Literal

from pydantic import BaseModel, Field


class SkeletonStatus(BaseModel):
    stage: Literal["foundation"] = "foundation"
    message: str = (
        "Accounts, portfolios and durable job runs are available. "
        "Marketplace connection is pending."
    )
    implemented: list[str] = Field(
        default_factory=lambda: [
            "API liveness, database readiness and OpenAPI",
            "Accounts, revocable sessions and user-owned profile settings",
            "Portfolio uploads, source revisions and background indexing",
            "Dense, hybrid, reranked and corrective evidence retrieval",
            "Tenant-bound Portfolio MCP tools and resources",
            "Manual-job inbox, proposal review and run activity screens",
            "Typed handoff contracts",
            "Postgres proposal checkpoints, ID-bound approvals and local draft commits",
            "Durable token/step accounting and persisted event streaming",
            "MCP registration scaffolds",
        ]
    )
    pending: list[str] = Field(
        default_factory=lambda: [
            "Distributed auth rate limiting and production deployment",
            "GigSim and Upwork adapters",
            "GitHub corpus ingestion and measured retrieval selection",
            "Conversation agents and memory persistence",
            "Provider authorization, idempotency and reconciliation",
            "Measured proposal quality and claim-verifier calibration",
            "Evaluation and deployment",
        ]
    )
