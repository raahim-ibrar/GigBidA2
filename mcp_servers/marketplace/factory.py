import os

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from agent.marketplace_port import MarketplaceResult, MessageWrite, ProposalWrite, SearchJobs
from agent.run_store import RunConflict, RunNotFound
from apps.api.database import make_engine
from apps.api.settings import Settings
from mcp_servers.marketplace.adapters.student_sim import MarketplaceRejected, MarketplaceUnavailable
from mcp_servers.marketplace.service import MarketplaceService


def create_marketplace_server(service=None, tenant_id=None, run_id=None):
    mcp = FastMCP("GigBid Marketplace")
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)
    write = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True)

    async def result(awaitable):
        try:
            return await awaitable
        except (RunConflict, RunNotFound, MarketplaceRejected) as error:
            return MarketplaceResult(
                provider="student_sim", data={"error": {"kind": "rejected", "message": str(error)}}
            )
        except MarketplaceUnavailable as error:
            return MarketplaceResult(
                provider="student_sim",
                data={"error": {"kind": "unavailable", "message": str(error)}},
            )

    def owner():
        nonlocal service
        if not tenant_id:
            raise ValueError("Set host-bound GIGBID_TENANT_ID")
        if service is None:
            settings = Settings()
            service = MarketplaceService(
                make_engine(settings.database_url), settings, tenant_id, run_id
            )
        return service

    @mcp.tool(annotations=read)
    async def search_jobs(request: SearchJobs) -> MarketplaceResult:
        """Search the connected student simulator's jobs; this cannot submit or spend."""
        return await result(owner().read("search_jobs", request))

    @mcp.tool(annotations=read)
    async def get_job(job_id: str) -> MarketplaceResult:
        """Read a simulator job by its provider ID; never returns private scenario labels."""
        return await result(owner().read("get_job", job_id))

    @mcp.tool(annotations=read)
    async def get_client_history(client_id: str) -> MarketplaceResult:
        """Read explicitly synthetic client history from the connected simulator."""
        return await result(owner().read("get_client_history", client_id))

    @mcp.tool(annotations=read)
    async def get_connects_balance() -> MarketplaceResult:
        """Read this host-bound account's simulated Connects balance."""
        return await result(owner().read("get_connects_balance"))

    @mcp.tool(annotations=read)
    async def list_messages(conversation_id: str) -> MarketplaceResult:
        """Read only this account's simulator conversation messages."""
        return await result(owner().read("list_messages", conversation_id))

    @mcp.tool(annotations=write)
    async def create_proposal_draft(request: ProposalWrite) -> MarketplaceResult:
        """Always preview a verified proposal and exact Connects charge without spending."""
        return await result(
            owner().write("submit_proposal", request.model_copy(update={"dry_run": True}))
        )

    @mcp.tool(annotations=write)
    async def submit_proposal(request: ProposalWrite) -> MarketplaceResult:
        """Preview by default; execution requires the run's exact latest human approval."""
        return await result(owner().write("submit_proposal", request))

    @mcp.tool(annotations=write)
    async def send_message(request: MessageWrite) -> MarketplaceResult:
        """Preview by default; send only an exactly approved reply to the simulator."""
        return await result(owner().write("send_message", request))

    return mcp


def configured_server():
    return create_marketplace_server(
        tenant_id=os.getenv("GIGBID_TENANT_ID"), run_id=os.getenv("GIGBID_RUN_ID")
    )
