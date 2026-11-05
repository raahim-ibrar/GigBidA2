"""Per-tenant MCP capabilities; tenant identity is never a model-controlled tool arg.

Import the numerical runtime before stdio starts its blocking reader. Lazy NumPy import
inside the first MCP request stalled on Windows; a real subprocess regression covers it.
"""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from agent.handoffs import EvidenceItem
from apps.api.database import make_engine
from apps.api.settings import Settings
from mcp_servers.portfolio import resources
from mcp_servers.portfolio.prompts import screening_prompt
from mcp_servers.portfolio.tools import EvidenceResult, SearchEvidence, SkillList
from rag.contracts import PortfolioSearch
from rag.runtime import build_portfolio
from rag.service import MissingEvidence


def create_portfolio_server(service=None, tenant_id: str | None = None):
    mcp = FastMCP("GigBid Portfolio")
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)

    def owner():
        nonlocal service
        if not tenant_id:
            raise ValueError(
                "Set GIGBID_TENANT_ID to your account ID before starting Portfolio MCP"
            )
        if service is None:
            settings = Settings()
            service = build_portfolio(make_engine(settings.database_url), settings)
        return service

    @mcp.tool(annotations=read)
    async def search_evidence(request: SearchEvidence) -> EvidenceResult:
        """Retrieve only this account's indexed evidence, with immutable source chunk IDs."""
        import asyncio

        result = await asyncio.to_thread(
            owner().search,
            tenant_id,
            PortfolioSearch(
                query=request.requirement,
                k=request.k,
                filters=request.filters,
                variant=request.variant,
            ),
        )
        return EvidenceResult(items=[hit.evidence for hit in result.items])

    @mcp.tool(annotations=read)
    async def get_case_study(id: str) -> EvidenceItem:
        """Read a full indexed source by document ID, or an individual evidence chunk by ID."""
        try:
            return owner().case_study(tenant_id, id)
        except MissingEvidence:
            return owner().evidence(tenant_id, id)

    @mcp.tool(annotations=read)
    async def list_skills() -> SkillList:
        """List skills declared in this account's indexed portfolio metadata."""
        return SkillList(skills=owner().skills(tenant_id))

    @mcp.resource("portfolio://case/{id}")
    async def case_resource(id: str) -> str:
        return resources.case_resource(owner(), tenant_id, id)

    @mcp.resource("portfolio://proposal/{id}")
    async def proposal_resource(id: str) -> str:
        return resources.proposal_resource(owner(), tenant_id, id)

    mcp.prompt(name="answer_screening_question")(screening_prompt)
    return mcp
