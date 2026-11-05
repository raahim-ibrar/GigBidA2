from agent.marketplace_port import MarketplaceResult, MessageWrite, ProposalWrite, SearchJobs


class GigSimAdapter:
    async def search_jobs(self, request: SearchJobs) -> MarketplaceResult:
        raise NotImplementedError("Implement gigsim.search_jobs against official schemas")

    async def get_job(self, job_id: str) -> MarketplaceResult:
        raise NotImplementedError("Implement gigsim.get_job against official schemas")

    async def get_client_history(self, client_id: str) -> MarketplaceResult:
        raise NotImplementedError("Implement gigsim.get_client_history against official schemas")

    async def get_connects_balance(self) -> MarketplaceResult:
        raise NotImplementedError("Implement gigsim.get_connects_balance against official schemas")

    async def list_messages(self, conversation_id: str) -> MarketplaceResult:
        raise NotImplementedError("Implement gigsim.list_messages against official schemas")

    async def create_proposal_draft(self, request: ProposalWrite) -> MarketplaceResult:
        raise NotImplementedError("Implement gigsim.create_proposal_draft against official schemas")

    async def submit_proposal(self, request: ProposalWrite) -> MarketplaceResult:
        raise NotImplementedError("Implement gigsim.submit_proposal against official schemas")

    async def send_message(self, request: MessageWrite) -> MarketplaceResult:
        raise NotImplementedError("Implement gigsim.send_message against official schemas")
