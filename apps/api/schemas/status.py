from typing import Literal

from pydantic import BaseModel, Field


class SkeletonStatus(BaseModel):
    stage: Literal["foundation"] = "foundation"
    message: str = (
        "Accounts, profiles and portfolio evidence search are working. Proposal agents are next."
    )
    implemented: list[str] = Field(
        default_factory=lambda: [
            "API liveness, database readiness and OpenAPI",
            "Accounts, revocable sessions and user-owned profile settings",
            "Portfolio uploads, source revisions and background indexing",
            "Dense, hybrid, reranked and corrective evidence retrieval",
            "Tenant-bound Portfolio MCP tools and resources",
            "TypeScript route shells",
            "Typed handoff contracts",
            "Injectable graph topologies",
            "MCP registration scaffolds",
        ]
    )
    pending: list[str] = Field(
        default_factory=lambda: [
            "Distributed auth rate limiting and production deployment",
            "GigSim and Upwork adapters",
            "GitHub corpus ingestion and measured retrieval selection",
            "Agent node implementations",
            "Postgres checkpointer lifecycle",
            "Durable worker execution and streaming",
            "Approval API and exactly-once marketplace writes",
            "Evaluation and deployment",
        ]
    )
