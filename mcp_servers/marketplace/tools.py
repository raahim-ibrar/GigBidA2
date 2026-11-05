from agent.marketplace_port import (
    MarketplaceResult,
    MessageWrite,
    ProposalWrite,
    SearchJobs,
)


def adapter():
    raise NotImplementedError(
        "Wire the configured marketplace port after auth, idempotency and audit storage exist"
    )


async def search_jobs(request: SearchJobs) -> MarketplaceResult:
    return await adapter().search_jobs(request)


async def get_job(job_id: str) -> MarketplaceResult:
    return await adapter().get_job(job_id)


async def get_client_history(client_id: str) -> MarketplaceResult:
    return await adapter().get_client_history(client_id)


async def get_connects_balance() -> MarketplaceResult:
    return await adapter().get_connects_balance()


async def list_messages(conversation_id: str) -> MarketplaceResult:
    return await adapter().list_messages(conversation_id)


async def create_proposal_draft(request: ProposalWrite) -> MarketplaceResult:
    return await adapter().create_proposal_draft(request)


async def submit_proposal(request: ProposalWrite) -> MarketplaceResult:
    return await adapter().submit_proposal(request)


async def send_message(request: MessageWrite) -> MarketplaceResult:
    return await adapter().send_message(request)
