import os

from agent.marketplace_port import (
    MarketplaceResult,
    MessageWrite,
    ProposalWrite,
    SearchJobs,
)
from apps.api.database import make_engine
from apps.api.settings import Settings
from mcp_servers.marketplace.service import MarketplaceService


def adapter():
    tenant = os.getenv("GIGBID_TENANT_ID")
    if not tenant:
        raise ValueError("Host-bound account identity required")
    settings = Settings()
    return MarketplaceService(
        make_engine(settings.database_url), settings, tenant, os.getenv("GIGBID_RUN_ID")
    )


async def search_jobs(request: SearchJobs) -> MarketplaceResult:
    return await adapter().read("search_jobs", request)


async def get_job(job_id: str) -> MarketplaceResult:
    return await adapter().read("get_job", job_id)


async def get_client_history(client_id: str) -> MarketplaceResult:
    return await adapter().read("get_client_history", client_id)


async def get_connects_balance() -> MarketplaceResult:
    return await adapter().read("get_connects_balance")


async def list_messages(conversation_id: str) -> MarketplaceResult:
    return await adapter().read("list_messages", conversation_id)


async def create_proposal_draft(request: ProposalWrite) -> MarketplaceResult:
    return await adapter().write("submit_proposal", request.model_copy(update={"dry_run": True}))


async def submit_proposal(request: ProposalWrite) -> MarketplaceResult:
    return await adapter().write("submit_proposal", request)


async def send_message(request: MessageWrite) -> MarketplaceResult:
    return await adapter().write("send_message", request)
