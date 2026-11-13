"""Validated capability wrapper over a host-bound Marketplace MCP session."""

from agent.marketplace_port import MarketplaceResult, MessageWrite, ProposalWrite, SearchJobs
from mcp_servers.marketplace.adapters.student_sim import MarketplaceRejected, MarketplaceUnavailable


class MarketplaceMCP:
    def __init__(self, session):
        self.session = session

    async def call(self, name, args=None):
        result = await self.session.call_tool(name, args or {})
        if result.isError or result.structuredContent is None:
            raise MarketplaceUnavailable(
                "Marketplace MCP unavailable or action rejected; "
                "check connection, approval and budget"
            )
        data = MarketplaceResult.model_validate(result.structuredContent).data
        if "error" in data:
            error = data["error"]
            kind = (
                MarketplaceRejected if error.get("kind") == "rejected" else MarketplaceUnavailable
            )
            raise kind(error.get("message", "Marketplace unavailable"))
        return data

    async def search(self, query, limit=20):
        return await self.call(
            "search_jobs", {"request": SearchJobs(query=query, limit=limit).model_dump()}
        )

    async def job(self, id):
        return await self.call("get_job", {"job_id": id})

    async def client(self, id):
        return await self.call("get_client_history", {"client_id": id})

    async def balance(self):
        return await self.call("get_connects_balance")

    async def pricing_statistics(self, job_id):
        return await self.call("get_pricing_statistics", {"job_id": job_id})

    async def messages(self, id):
        return await self.call("list_messages", {"conversation_id": id})

    async def proposal(self, request: ProposalWrite):
        return await self.call(
            "create_proposal_draft" if request.dry_run else "submit_proposal",
            {"request": request.model_dump()},
        )

    async def message(self, request: MessageWrite):
        return await self.call("send_message", {"request": request.model_dump()})
