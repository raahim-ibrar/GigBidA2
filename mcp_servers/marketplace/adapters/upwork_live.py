"""Verified Upwork MCP mappings; no final submission or direct-message capability."""

import asyncio
import json
import re
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from agent.marketplace_port import MarketplaceResult
from agent.mcp_audit import ReadAuditor
from apps.api.auth.token_store import EncryptedTokenStorage, OAuthUnavailable
from apps.api.models import OAuthCredential
from mcp_servers.marketplace.adapters.student_sim import MarketplaceRejected, MarketplaceUnavailable
from mcp_servers.marketplace.upwork_transport import upwork_session

# Exact names/actions observed from the authorized official tools/list + get_tool_help.
CAPABILITIES = {
    "search_jobs": ("upwork__find_jobs", "search"),
    "get_job": ("upwork__find_jobs", "get"),
    "get_client_history": ("upwork__find_jobs", "get"),
    "get_connects_balance": ("upwork__get_freelancer_financials", "connects_balance"),
    "list_messages": ("upwork__get_messages", "list_messages"),
    "create_proposal_draft": ("upwork__manage_proposals", "create"),
}


def verified_capabilities(tools):
    available = {t.name: t.model_dump(mode="json") for t in tools}
    return {
        cap: {"tool": name, "action": action}
        for cap, (name, action) in CAPABILITIES.items()
        if name in available
        and action
        in available[name]["inputSchema"].get("properties", {}).get("action", {}).get("enum", [])
    }


def parse_result(result):
    if result.isError:
        raise MarketplaceUnavailable(
            "Upwork rejected the request; check connection, capabilities and job eligibility"
        )
    if result.structuredContent is not None:
        data = result.structuredContent
    else:
        try:
            data = json.loads(next(c.text for c in result.content if c.type == "text"))
        except (ValueError, StopIteration):
            raise MarketplaceUnavailable("Unexpected Upwork response schema") from None
    if not isinstance(data, dict) or data.get("error") or data.get("status") in ["error", "failed"]:
        raise MarketplaceUnavailable(
            "Upwork returned an error; reconnect or inspect the saved request"
        )
    return data


def safe_job_url(value):
    parts = urlparse(value or "")
    return (
        value
        if parts.scheme == "https"
        and parts.netloc in ["www.upwork.com", "upwork.com"]
        and parts.path.startswith("/jobs/")
        else None
    )


def normalize_job(raw, generation, *, detail=None):
    detail = detail or {}
    amounts = [
        float(n.replace(",", ""))
        for n in re.findall(r"\d[\d,]*(?:\.\d+)?", str(raw.get("budget", "")))
    ]
    billing = raw.get("job_type", "unknown").lower()
    low, high = (amounts[0], amounts[-1]) if amounts else (None, None)
    identity = str(raw.get("id", ""))
    if (
        not identity
        or not isinstance(raw.get("title"), str)
        or not isinstance(raw.get("description"), str)
    ):
        raise MarketplaceUnavailable("Incomplete Upwork job record")
    return {
        "id": identity,
        "source": "upwork",
        "synthetic": False,
        "connection_generation": generation,
        "title": raw["title"][:200],
        "description": raw["description"][:12000],
        "billing_type": billing if billing in ["hourly", "fixed"] else "unknown",
        "budget_min": low,
        "budget_max": high,
        "currency": "USD",
        "skills": raw.get("skills", []),
        "client_id": identity,
        "client": raw.get("client", {}),
        "url": safe_job_url(raw.get("url")),
        "connects_cost": detail.get("connects_cost", raw.get("connect_price")),
        "can_apply": detail.get("can_apply"),
        "applied": detail.get("applied", raw.get("applied", False)),
        "screening_questions": raw.get("screening_questions", []),
    }


def detail_job(data, generation):
    try:
        job = data["data"]["marketplaceJobPosting"]
        terms = job.get("contractTerms", {})
        hourly = terms.get("hourlyContractTerms", {})
        fixed = terms.get("fixedPriceContractTerms", {})
        billing = terms.get("contractType", "unknown").lower()
        raw = {
            "id": job["id"],
            "title": job["content"]["title"],
            "description": job["content"]["description"],
            "url": job.get("url"),
            "job_type": billing,
            "client": job.get("clientCompanyPublic", {}),
            "budget": str(hourly.get("hourlyBudgetMin", ""))
            + "-"
            + str(hourly.get("hourlyBudgetMax", ""))
            if billing == "hourly"
            else str(fixed.get("amount", fixed.get("budget", ""))),
            "screening_questions": job.get("screeningQuestions", []),
        }
        return normalize_job(raw, generation, detail=data)
    except (KeyError, TypeError):
        raise MarketplaceUnavailable(
            "Upwork job details changed schema; reconnect for discovery"
        ) from None


class UpworkLiveAdapter:
    def __init__(
        self, engine, settings, tenant, *, generation=None, session_factory=upwork_session
    ):
        self.engine, self.settings, self.tenant = engine, settings, tenant
        self.session_factory = session_factory
        with Session(engine) as db:
            row = db.get(OAuthCredential, (tenant, "upwork"))
            if not row or not row.connected:
                raise MarketplaceUnavailable("Authorize Upwork on the host laptop first")
            if generation and generation != row.generation:
                raise MarketplaceRejected("Upwork connection changed; start a new run")
            self.generation = row.generation
            self.schemas = {s["name"]: s for s in row.schema_snapshot}

    async def _call(self, name, action=None, params=None, *, prepare=False):
        allowed = {v for k, v in CAPABILITIES.items() if k != "create_proposal_draft"}
        allowed.add(("upwork__list_freelancer_proposals", "list"))
        allowed.add(("upwork__list_freelancer_proposals", "invitations"))
        if prepare:
            allowed.add(CAPABILITIES["create_proposal_draft"])
        if (name, action) not in allowed:
            raise MarketplaceRejected(
                "Final submission, direct messages and arbitrary Upwork actions are disabled"
            )
        try:
            storage = EncryptedTokenStorage(
                self.engine, self.settings, self.tenant, generation=self.generation
            )
            account = await asyncio.to_thread(storage.read)
            if not account.get("org_uid"):
                raise OAuthUnavailable("Select a freelancer account with the local sign-in helper")
            async with self.session_factory(
                self.engine, self.settings, self.tenant, generation=self.generation
            ) as (session, _):
                actual = {
                    t.name: t.model_dump(mode="json") for t in (await session.list_tools()).tools
                }
                expected = self.schemas.get(name)
                if (
                    not expected
                    or name not in actual
                    or actual[name]["inputSchema"] != expected["inputSchema"]
                ):
                    raise MarketplaceRejected(
                        "Upwork tool schema changed; reconnect to verify new capabilities"
                    )
                if not prepare and not (actual[name].get("annotations") or {}).get("readOnlyHint"):
                    raise MarketplaceRejected(
                        "Upwork changed this read capability; review the integration"
                    )
                enum = (
                    actual[name]["inputSchema"]
                    .get("properties", {})
                    .get("action", {})
                    .get("enum", [])
                )
                if action not in enum:
                    raise MarketplaceRejected("This Upwork action is not available")
                arguments = {
                    "action": action,
                    "org_uid": account["org_uid"],
                    "params": params or {},
                }
                if prepare:
                    result = await session.call_tool(name, arguments)
                else:
                    result = await ReadAuditor(self.engine, self.tenant).invoke(
                        "upwork",
                        name,
                        arguments,
                        lambda: session.call_tool(name, arguments),
                    )
                return parse_result(result)
        except (MarketplaceRejected, MarketplaceUnavailable):
            raise
        except Exception:
            raise MarketplaceUnavailable(
                "Upwork unavailable or authorization expired; reconnect on the host laptop"
            ) from None

    async def search_jobs(self, request):
        data = await self._call(
            *CAPABILITIES["search_jobs"],
            {"query": request.query, "limit": min(request.limit, 10), "include_full_details": True},
        )
        if not isinstance(data.get("jobs"), list):
            raise MarketplaceUnavailable("Upwork search response changed schema")
        return MarketplaceResult(
            provider="upwork",
            data={
                "items": [normalize_job(j, self.generation) for j in data["jobs"]],
                "has_more": bool(data.get("hasMore")),
                "next_cursor": data.get("next_cursor"),
            },
        )

    async def get_job(self, job_id):
        data = await self._call(*CAPABILITIES["get_job"], {"id": job_id})
        return MarketplaceResult(provider="upwork", data=detail_job(data, self.generation))

    async def get_client_history(self, client_id):
        data = await self._call(*CAPABILITIES["get_client_history"], {"id": client_id})
        return MarketplaceResult(
            provider="upwork",
            data={
                "source": "upwork",
                "synthetic": False,
                "client": data.get("data", {})
                .get("marketplaceJobPosting", {})
                .get("clientCompanyPublic", {}),
                "record": data.get("client_record", {}),
                "limitations": "Public Upwork details only; missing fields are unknown.",
            },
        )

    async def get_connects_balance(self):
        data = await self._call(*CAPABILITIES["get_connects_balance"])
        value = data.get("balance", {}).get("connectsBalance")
        if not isinstance(value, int) or value < 0:
            raise MarketplaceUnavailable("Upwork balance is unavailable")
        return MarketplaceResult(provider="upwork", data={"connects": value, "synthetic": False})

    async def list_messages(self, conversation_id):
        data = await self._call(
            *CAPABILITIES["list_messages"], {"room_id": conversation_id, "limit": 20}
        )
        return MarketplaceResult(provider="upwork", data=data)

    async def create_proposal_draft(self, request):
        job = (await self.get_job(request.job_id)).data
        cost = job.get("connects_cost")
        if type(cost) is not int or cost < 0:
            raise MarketplaceRejected("Upwork did not provide a verified Connects cost")
        if job.get("applied"):
            raise MarketplaceRejected("An application already exists for this job")
        if len(request.text) > 5000:
            raise MarketplaceRejected(
                "Upwork cover letters must be at most 5,000 characters; edit before approval"
            )
        return MarketplaceResult(
            provider="upwork",
            data={
                "connects_cost": cost,
                "final_submission_enabled": False,
                "effect": "prepare_upwork_preview_only",
                "job_url": job.get("url"),
                "can_apply": job.get("can_apply"),
            },
        )

    async def prepare_approved_proposal(self, request, *, approved_cost):
        # Called only by MarketplaceService after exact approval and a durable send-once intent.
        preflight = (await self.create_proposal_draft(request)).data
        if preflight["connects_cost"] != approved_cost:
            raise MarketplaceRejected(
                "Upwork Connects cost changed after approval; review a new quote"
            )
        for action in ["invitations", "list"]:
            existing = await self._call("upwork__list_freelancer_proposals", action, {"limit": 10})
            # Cannot assert absence beyond a partial page; fail closed.
            if existing.get("hasMore"):
                raise MarketplaceRejected(
                    "Review existing invitations/proposals on Upwork first; results are paginated"
                )
            if request.job_id in json.dumps(existing):
                raise MarketplaceRejected("Existing invitation/proposal requires review on Upwork")
        data = await self._call(
            *CAPABILITIES["create_proposal_draft"],
            {
                "job_reference": request.job_id,
                "cover_letter": request.text,
                "charged_amount": request.bid_amount,
                "answers": [
                    {"question": q, "answer": a} for q, a in request.screening_answers.items()
                ],
            },
            prepare=True,
        )
        if not isinstance(data.get("preview_id"), str):
            raise MarketplaceUnavailable(
                "Provider preview outcome unknown; do not repeat the action automatically"
            )
        return {
            "status": "pending_provider_confirmation",
            "provider": "upwork",
            "preview_id": data["preview_id"],
            "preview_type": "proposal",
            "connects_spent": 0,
            "connects_cost": data.get("connects_cost"),
            "note": "Not submitted. Final confirmation is disabled in GigBid; review on Upwork.",
            "job_url": preflight.get("job_url"),
        }

    async def submit_proposal(self, request):
        raise MarketplaceRejected("Final Upwork proposal submission is disabled")

    async def send_message(self, request):
        raise MarketplaceRejected(
            "Upwork sends messages directly; use a local draft and send it yourself on Upwork"
        )

    async def events(self, after=0):
        raise MarketplaceRejected("Upwork has no verified compatible lifecycle event feed")

    async def get_proposal(self, proposal_id):
        raise MarketplaceRejected("No compatible confirmed-receipt mapping is enabled")
