"""Both marketplace adapters implement this port. Agents access it only via MCP tools."""

from typing import Protocol

from pydantic import Field

from agent.handoffs import Contract


class SearchJobs(Contract):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=20, ge=1, le=100)


class ProposalWrite(Contract):
    job_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=20000)
    bid_amount: float = Field(gt=0)
    screening_answers: dict[str, str] = Field(default_factory=dict, max_length=20)
    idempotency_key: str = Field(min_length=8, max_length=200)
    dry_run: bool = True

    def arguments(self):
        return self.model_dump(exclude={"dry_run", "idempotency_key"})


class MessageWrite(Contract):
    conversation_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=10000)
    idempotency_key: str = Field(min_length=8, max_length=200)
    dry_run: bool = True


class MarketplaceResult(Contract):
    provider: str
    data: dict


class MarketplacePort(Protocol):
    async def search_jobs(self, request: SearchJobs) -> MarketplaceResult: ...
    async def get_job(self, job_id: str) -> MarketplaceResult: ...
    async def get_client_history(self, client_id: str) -> MarketplaceResult: ...
    async def get_connects_balance(self) -> MarketplaceResult: ...
    async def list_messages(self, conversation_id: str) -> MarketplaceResult: ...
    async def create_proposal_draft(self, request: ProposalWrite) -> MarketplaceResult: ...
    async def submit_proposal(self, request: ProposalWrite) -> MarketplaceResult: ...
    async def send_message(self, request: MessageWrite) -> MarketplaceResult: ...
    async def events(self, after: int = 0) -> MarketplaceResult: ...
    async def get_proposal(self, proposal_id: str) -> MarketplaceResult: ...
