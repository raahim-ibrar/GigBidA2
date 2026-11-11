"""HTTP adapter for our declared student simulator; never aliases instructor GigSim."""

import httpx

from agent.marketplace_port import MarketplaceResult


class MarketplaceUnavailable(RuntimeError):
    pass


class MarketplaceRejected(ValueError):
    pass


class StudentSimAdapter:
    def __init__(self, base_url, api_key, tenant, *, transport=None):
        self.base_url, self.api_key, self.tenant, self.transport = (
            base_url,
            api_key,
            tenant,
            transport,
        )

    async def request(self, method, path, **kwargs):
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=15,
                transport=self.transport,
                headers={"Authorization": "Bearer " + self.api_key, "X-Tenant-ID": self.tenant},
            ) as client:
                response = await client.request(method, path, **kwargs)
            if response.status_code == 429 or response.status_code >= 500:
                raise MarketplaceUnavailable(
                    "Student simulator temporarily unavailable; retry after recovery"
                )
            if response.status_code >= 400:
                raise MarketplaceRejected(
                    "Student simulator rejected the request (check record, balance and idempotency)"
                )
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Invalid simulator response")
            return MarketplaceResult(provider="student_sim", data=data)
        except (httpx.HTTPError, ValueError) as error:
            if isinstance(error, MarketplaceRejected):
                raise
            raise MarketplaceUnavailable("Student simulator response unavailable") from None

    async def search_jobs(self, request):
        return await self.request(
            "GET", "/jobs", params={"q": request.query, "limit": request.limit}
        )

    async def get_job(self, job_id):
        from urllib.parse import quote

        return await self.request("GET", "/jobs/" + quote(job_id, safe=""))

    async def get_client_history(self, client_id):
        from urllib.parse import quote

        return await self.request("GET", "/clients/" + quote(client_id, safe=""))

    async def get_connects_balance(self):
        return await self.request("GET", "/balance")

    async def list_messages(self, conversation_id):
        from urllib.parse import quote

        return await self.request(
            "GET", "/conversations/" + quote(conversation_id, safe="") + "/messages"
        )

    async def create_proposal_draft(self, request):
        return await self.request("POST", "/proposals/preview", json=request.model_dump())

    async def submit_proposal(self, request):
        return await self.request("POST", "/proposals", json=request.model_dump())

    async def send_message(self, request):
        return await self.request("POST", "/messages", json=request.model_dump())

    async def events(self, after=0):
        return await self.request("GET", "/events", params={"after": after})

    async def get_proposal(self, id):
        from urllib.parse import quote

        return await self.request("GET", "/proposals/" + quote(id, safe=""))
