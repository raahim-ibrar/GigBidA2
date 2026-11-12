"""Narrow read capability over a tenant-bound MCP session, never a database handle."""

from typing import Protocol

from agent.handoffs import EvidenceItem
from mcp_servers.portfolio.tools import EvidenceResult


class PortfolioReader(Protocol):
    async def search(self, query: str, *, k: int, variant: str) -> list[EvidenceItem]: ...

    async def read(self, evidence_id: str) -> EvidenceItem: ...


class PortfolioMCP:
    def __init__(self, session):
        # The host chooses this session's tenant. Tools cannot select another tenant.
        self.session = session

    async def _call(self, name: str, arguments: dict):
        result = await self.session.call_tool(name, arguments)
        if result.isError or result.structuredContent is None:
            raise RuntimeError("Portfolio MCP could not return validated evidence")
        return result.structuredContent

    async def search(self, query: str, *, k: int, variant: str) -> list[EvidenceItem]:
        result = await self._call(
            "search_evidence", {"request": {"requirement": query, "k": k, "variant": variant}}
        )
        return EvidenceResult.model_validate(result).items

    async def read(self, evidence_id: str) -> EvidenceItem:
        return EvidenceItem.model_validate(await self._call("get_case_study", {"id": evidence_id}))
