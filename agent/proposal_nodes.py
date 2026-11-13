"""Evidence-grounded bid nodes. The host supplies inference, MCP and a local executor.

This manual-job path cannot submit to a marketplace. Unknown client history, Connects
cost and instructor policy are explicit; none are fabricated from a model response.
"""

import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from decimal import Decimal

from pydantic import Field, field_validator

from agent.config import AgentConfig
from agent.handoffs import (
    BidDecision,
    Claim,
    ComplianceVerdict,
    Contract,
    Critique,
    FitReport,
    JobSpec,
    PriceQuote,
    ProposalDraft,
    RiskReport,
    WritePreview,
)
from agent.portfolio_client import PortfolioReader
from agent.proposal_contracts import FitAssessment, Verification
from agent.safety import EMAIL, EXPERIENCE, GUARANTEE, INJECTION, OFF_PLATFORM, PHONE


class GroundingFailure(RuntimeError):
    pass


class ReviewRequired(RuntimeError):
    pass


def sentences(text: str) -> list[str]:
    # Preserve exact wording. Newlines also delimit bullets; decimals stay intact.
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]


def normalized(text):
    return re.sub(r"\s+", " ", text).strip().casefold()


def draft_digest(draft: ProposalDraft) -> str:
    return hashlib.sha256(
        json.dumps(draft.model_dump(), sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def claim_is_verified(claim: Claim) -> bool:
    factual = claim.kind == "experience" or bool(EXPERIENCE.search(claim.text))
    if factual:
        return claim.verdict == "supported" and bool(claim.evidence_ids)
    return claim.verdict in {"supported", "not_applicable"}


def paragraph_spans(text):
    return [match.span() for match in re.finditer(r"\S[\s\S]*?(?=\n[ \t\r]*\n|\Z)", text)]


class ParagraphRewrite(Contract):
    text: str = Field(min_length=1, max_length=5000)

    @field_validator("text")
    @classmethod
    def single_paragraph(cls, value):
        value = value.strip()
        if not value or re.search(r"\n[ \t\r]*\n", value):
            raise ValueError("Return exactly one nonblank paragraph")
        return value


class ProposalNodes:
    def __init__(
        self,
        models,
        portfolio: PortfolioReader,
        config: AgentConfig,
        *,
        execute_local: Callable[[dict], Awaitable[dict]],
        load_memory=None,
        marketplace=None,
    ):
        self.models, self.portfolio, self.config = models, portfolio, config
        self.execute_local = execute_local
        self.load_memory = load_memory
        self.marketplace = marketplace

    def mapping(self):
        return {
            name: getattr(self, name)
            for name in (
                "scout",
                "analyst",
                "risk",
                "matcher",
                "decision",
                "pricing",
                "writer",
                "regenerate",
                "verifier",
                "critic",
                "compliance",
                "preview",
                "execute",
            )
        }

    async def scout(self, state):
        raw = state["raw_job"]
        if raw.get("source") in {"student_sim", "upwork"}:
            if not self.marketplace:
                raise ReviewRequired("Connect this job's original marketplace before analysing it")
            current = await self.marketplace.job(raw["provider_job_id"])
            if current.get("id") != raw["provider_job_id"]:
                raise ReviewRequired("Marketplace job identity changed")
            if raw.get("source") == "upwork":
                raw = current
        elif raw.get("source") != "manual":
            raise ReviewRequired("This marketplace source is not supported")
        if not raw.get("title", "").strip() or not raw.get("description", "").strip():
            raise ReviewRequired("A job title and description are required")
        if len(json.dumps(raw)) > 20000:
            raise ReviewRequired("Shorten the job post before analysing it")
        memory = await self.load_memory() if self.load_memory else {}
        return {"status": "analysing", "raw_job": raw, "memory": memory, "events": ["job_loaded"]}

    async def analyst(self, state):
        job = await self.models.complete("analyst", {"job": state["raw_job"]}, JobSpec)
        # The model never assigns authoritative identity or budget metadata.
        raw = state["raw_job"]
        job = JobSpec.model_validate(
            {
                **job.model_dump(),
                "job_id": state["job_id"],
                "title": raw["title"],
                "billing_type": raw.get("billing_type", "unknown"),
                "budget_min": raw.get("budget_min"),
                "budget_max": raw.get("budget_max"),
                "screening_questions": raw.get("screening_questions", job.screening_questions),
            }
        )
        if not job.requirements or len(job.requirements) > 20:
            raise ReviewRequired("The job needs between one and twenty clear requirements")
        return {"job": job, "events": ["job_analysed"]}

    async def risk(self, state):
        raw = state["raw_job"]
        history = await self.marketplace.client(raw["client_id"]) if self.marketplace else None
        report = await self.models.complete(
            "risk",
            {
                "job": raw,
                "client_history": history,
                "history_status": (
                    "Upwork public client details"
                    if raw.get("source") == "upwork"
                    else "synthetic student simulator"
                )
                if history
                else "unavailable",
            },
            RiskReport,
        )
        text = json.dumps(raw)
        flags = list(report.flags)
        if INJECTION.search(text):
            flags.append("prompt_injection")
        if OFF_PLATFORM.search(text):
            flags.append("off_platform_or_unpaid_work")
        hard_flag = any(f in flags for f in ("prompt_injection", "off_platform_or_unpaid_work"))
        return {
            "risk": RiskReport(
                score=max(report.score, 1.0 if hard_flag else 0.0),
                flags=list(dict.fromkeys(flags)),
                reasons=[
                    *report.reasons,
                    (
                        "Client history contains only available public Upwork fields."
                        if raw.get("source") == "upwork"
                        else "Client history is synthetic student-simulator data."
                    )
                    if history
                    else "Client history is unavailable for a manually entered job.",
                ],
            ),
            "events": ["risk_assessed"],
        }

    async def matcher(self, state):
        # Runs concurrently with Analyst: it must read the raw post, not Analyst's output.
        raw = state["raw_job"]
        query = (raw["title"] + "\n" + raw["description"])[:4000]
        evidence = await self.portfolio.search(
            query,
            k=self.config.retrieval["top_k"],
            variant=self.config.retrieval["variant"],
        )
        if raw.get("source") == "upwork":
            evidence = [
                item
                for item in evidence
                if not any(
                    marker in item.text.casefold()
                    for marker in ("synthetic persona", "fictional", "synthetic prototype")
                )
            ]
        return {"evidence": evidence, "events": ["portfolio_retrieved"]}

    async def decision(self, state):
        # Reconcile only after all parallel branches join. Coverage uses Analyst's final
        # requirements and only IDs actually returned by this tenant's Portfolio MCP.
        requirements = list(dict.fromkeys(state["job"].requirements))
        evidence = state.get("evidence", [])
        assessment = await self.models.complete(
            "matcher",
            {
                "requirements": requirements,
                "evidence": [item.model_dump() for item in evidence],
            },
            FitAssessment,
        )
        valid = {item.id for item in evidence}
        matrix = {
            requirement: list(
                dict.fromkeys(
                    item
                    for item in assessment.requirement_evidence.get(requirement, [])
                    if item in valid
                )
            )
            for requirement in requirements
        }
        gaps = [requirement for requirement, ids in matrix.items() if not ids]
        score = (len(requirements) - len(gaps)) / len(requirements)
        fit = FitReport(score=score, requirement_evidence=matrix, gaps=gaps)
        if state["risk"].score >= self.config.policy["maximum_risk"]:
            decision = BidDecision(
                action="skip", reasons=["Risk exceeds the configured threshold."]
            )
        elif score < self.config.policy["minimum_fit"] or not evidence:
            decision = BidDecision(action="watch", reasons=["Insufficient portfolio evidence."])
        else:
            decision = BidDecision(
                action="bid",
                reasons=[
                    f"Portfolio evidence covers {len(requirements) - len(gaps)}"
                    f"/{len(requirements)} "
                    + (
                        "requirements; student simulator submission requires approval."
                        if self.marketplace
                        else "requirements; local draft review only."
                    ),
                ],
            )
        return {"fit": fit, "decision": decision, "events": ["bid_decided"]}

    async def pricing(self, state):
        job = state["job"]
        if job.billing_type == "unknown":
            raise ReviewRequired("Specify whether this job is hourly or fixed price")
        if job.budget_max is None or job.budget_max <= 0:
            raise ReviewRequired("Enter the client's budget before requesting a quote")
        if state["raw_job"].get("currency", "USD") != "USD":
            raise ReviewRequired(
                "USD pricing requires a USD budget; currency conversion is unavailable"
            )
        floor = max(
            Decimal(str(state.get("preferences", {}).get("hourly_floor", 15))),
            Decimal(str(self.config.policy["minimum_hourly_rate_usd"])),
        )
        # Work in whole cents while preserving fractional configured rate floors.
        floor = floor.quantize(Decimal("0.01"), rounding="ROUND_CEILING")
        lower = Decimal(str(job.budget_min or 0))
        if job.billing_type == "hourly":
            lower = max(lower, floor)
        lower = lower.quantize(Decimal("0.01"), rounding="ROUND_CEILING")
        upper = Decimal(str(job.budget_max)).quantize(Decimal("0.01"), rounding="ROUND_DOWN")
        if lower > upper:
            raise ReviewRequired(
                "The client's budget cannot meet your minimum rate or price precision"
            )
        from agent.pricing import reference_price
        from mcp_servers.marketplace.adapters.student_sim import (
            MarketplaceRejected,
            MarketplaceUnavailable,
        )

        reference, rationale = (
            None,
            "Market and client price history unavailable; using the entered budget.",
        )
        if self.marketplace:
            try:
                statistics = await self.marketplace.pricing_statistics(
                    state["raw_job"]["provider_job_id"]
                )
                reference, rationale = reference_price(statistics, job.billing_type)
            except (MarketplaceUnavailable, MarketplaceRejected):
                rationale = "Pricing statistics temporarily unavailable; using the entered budget."
        amount = Decimal(
            str(reference if reference is not None else job.budget_min or job.budget_max)
        )
        amount = min(max(amount, lower), upper)
        amount = amount.quantize(Decimal("0.01"), rounding="ROUND_DOWN")
        if amount <= 0 or (job.billing_type == "hourly" and amount < floor):
            raise ReviewRequired(
                "No valid cent-denominated quote meets your minimum rate and budget"
            )
        connects = state["raw_job"].get("connects_cost") if self.marketplace else None
        if self.marketplace:
            balance = await self.marketplace.balance()
            if (
                type(connects) is not int
                or connects < 0
                or type(balance.get("connects")) is not int
                or connects > balance["connects"]
            ):
                raise ReviewRequired(
                    "Marketplace Connects cost is unknown or the balance is insufficient"
                )
        return {
            "price": PriceQuote(
                amount=float(amount),
                billing_type=job.billing_type,
                connects=connects,
                rationale=rationale
                + " Quote constrained to the posted budget"
                + (
                    " and your hourly rate floor."
                    if job.billing_type == "hourly"
                    else "; fixed scope/effort still needs review."
                )
                + (
                    " Provider Connects cost and balance checked."
                    if self.marketplace
                    else " Connects cost unavailable for manual jobs."
                ),
            ),
            "events": ["price_proposed"],
        }

    async def regenerate(self, state):
        draft = state["draft"]
        spans = paragraph_spans(draft.text)
        index = state["approval"].paragraph_index
        if index is None or index >= len(spans):
            raise ReviewRequired("Selected paragraph is no longer available")
        start, end = spans[index]
        replacement = await self.models.complete(
            "writer",
            {
                "task": "regenerate_one_paragraph",
                "job": state["job"].model_dump(),
                "verified_draft": draft.text,
                "selected_paragraph": draft.text[start:end],
                "portfolio_evidence": [item.model_dump() for item in state.get("evidence", [])],
                "quote": state["price"].model_dump(),
            },
            ParagraphRewrite,
        )
        text = draft.text[:start] + replacement.text + draft.text[end:]
        if len(text) > 20000:
            raise ReviewRequired("Regenerated cover letter is too long")
        return {
            "draft": ProposalDraft(text=text, screening_answers=draft.screening_answers),
            "user_edited": True,
            "status": "editing",
            "events": ["paragraph_regenerated"],
        }

    async def writer(self, state):
        draft = await self.models.complete(
            "writer",
            {
                "task": "draft_proposal",
                "job": state["job"].model_dump(),
                "fit": state["fit"].model_dump(),
                "evidence": [item.model_dump() for item in state.get("evidence", [])],
                "quote": state["price"].model_dump(),
                "critique": state["critique"].model_dump() if state.get("critique") else None,
                "previous_draft": state["draft"].model_dump() if state.get("draft") else None,
                "promoted_memory": state.get("memory", {}),
                "proposal_strategy": state.get("proposal_strategy", "problem_first"),
            },
            ProposalDraft,
        )
        # Recover only punctuation/case differences in an otherwise identical question.
        # Never guess which unrelated question an answer belongs to.
        questions = state["job"].screening_questions
        canonical = {normalized(question).rstrip("?.!"): question for question in questions}
        if len(canonical) == len(questions):
            answers = {
                canonical.get(normalized(key).rstrip("?.!"), key): value
                for key, value in draft.screening_answers.items()
            }
            if len(answers) == len(draft.screening_answers):
                draft = draft.model_copy(update={"screening_answers": answers})
        # Writer-provided claim labels are untrusted. Rebuild them from the actual text.
        return {
            "draft": draft.model_copy(update={"claims": []}),
            "status": "drafting",
            "events": ["draft_written"],
        }

    async def verifier(self, state):
        draft = state["draft"]
        answer_keys = list(draft.screening_answers)
        sections = [(0, sentences(draft.text))] + [
            (index + 1, sentences(draft.screening_answers[key]))
            for index, key in enumerate(answer_keys)
        ]
        units = [(section, text) for section, parts in sections for text in parts]
        if not units or len(units) > 80:
            raise GroundingFailure("The draft is empty or too long to verify")
        # Re-read immutable chunks: deleted or superseded sources must fail closed.
        evidence = [await self.portfolio.read(item.id) for item in state.get("evidence", [])]
        review = await self.models.complete(
            "verifier",
            {
                "sentences": [{"index": i, "text": text} for i, (_, text) in enumerate(units)],
                "evidence": [item.model_dump() for item in evidence],
            },
            Verification,
        )
        by_index = {item.index: item for item in review.claims}
        if len(by_index) != len(review.claims) or set(by_index) != set(range(len(units))):
            raise GroundingFailure("The verifier did not assess every draft sentence exactly once")
        valid = {item.id for item in evidence}
        kept: dict[int, list[str]] = {key: [] for key, _ in sections}
        claims, removed = [], []
        for index, (section, text) in enumerate(units):
            checked = by_index[index]
            ids = list(dict.fromkeys(item for item in checked.evidence_ids if item in valid))
            kind = "experience" if EXPERIENCE.search(text) else checked.kind
            if kind == "non_experience" and checked.verdict == "not_applicable":
                ids = []
            if kind == "experience" and checked.verdict == "supported" and not ids:
                # Models sometimes omit IDs even for verbatim excerpts. Bind only an
                # exact normalized substring of an actual source, never a free-text
                # citation in the model's explanation or an inferred paraphrase.
                ids = [item.id for item in evidence if normalized(text) in normalized(item.text)]
            supported = (
                checked.verdict == "supported" and (kind != "experience" or bool(ids))
            ) or (kind == "non_experience" and checked.verdict == "not_applicable")
            reason = checked.reason
            if supported and kind == "experience":
                cited = " ".join(item.text for item in evidence if item.id in ids)
                # A conservative extra check: numerical experience/results must appear
                # in cited text, even if the probabilistic verifier said 'supported'.
                # A source UUID cited in prose is an identifier, not a metric claim.
                # Only remove exact IDs from the trusted evidence set before checking numbers.
                numeric_text = text
                for source_id in valid:
                    numeric_text = numeric_text.replace(source_id, "")
                numbers = re.findall(r"\b\d+(?:[.,]\d+)*%?", numeric_text)
                cited_numbers = set(re.findall(r"\b\d+(?:[.,]\d+)*%?", cited))
                supported = set(numbers) <= cited_numbers
                if not supported:
                    reason = "The cited text does not contain the claimed number."
                elif re.search(r"\brecent(?:ly)?\b", text, re.I) and not re.search(
                    r"\brecent(?:ly)?\b", cited, re.I
                ):
                    supported = False
                    reason = "The cited text does not support the claim of recency."
            if not supported:
                removed.append({"index": index, "reason": reason})
                continue
            kept[section].append(text)
            claims.append(
                Claim(
                    text=text,
                    evidence_ids=ids,
                    kind=kind,
                    verdict="not_applicable"
                    if checked.verdict == "not_applicable"
                    else "supported",
                    reason=checked.reason,
                )
            )
        if not kept[0]:
            raise GroundingFailure(
                "No verified cover text remains; add portfolio evidence or revise"
            )
        # Do not silently return blank answers to screening questions.
        if any(not kept[index + 1] for index in range(len(answer_keys))):
            raise GroundingFailure(
                "A screening answer has no supported text; revise it before review"
            )
        if removed and state.get("approval") and state["approval"].action == "regenerate":
            raise GroundingFailure(
                "Regeneration cannot retain every verified claim; "
                "inspect the replacement and source evidence"
            )
        verified = ProposalDraft(
            text=draft.text if len(kept[0]) == len(sections[0][1]) else "\n".join(kept[0]),
            claims=claims,
            screening_answers={
                key: draft.screening_answers[key]
                if len(kept[index + 1]) == len(sections[index + 1][1])
                else "\n".join(kept[index + 1])
                for index, key in enumerate(answer_keys)
            },
        )
        return {
            "draft": verified,
            "evidence": evidence,
            "verification": {"removed": removed, "assessed_sentences": len(units)},
            "events": ["claims_verified"],
        }

    async def critic(self, state):
        critique = await self.models.complete(
            "critic",
            {
                "job": state["job"].model_dump(),
                "draft": state["draft"].model_dump(),
                "fit": state["fit"].model_dump(),
                "verification": state["verification"],
            },
            Critique,
        )
        if set(state["draft"].screening_answers) != set(state["job"].screening_questions):
            critique = Critique(
                verdict="revise", reasons=["Answer every screening question exactly."]
            )
        return {"critique": critique, "events": ["draft_critiqued"]}

    async def compliance(self, state):
        draft = state["draft"]
        text = "\n".join([draft.text, *draft.screening_answers.values()])
        rules = (
            (EMAIL, "contact_email"),
            (PHONE, "contact_phone"),
            (GUARANTEE, "unsupported_guarantee"),
            (OFF_PLATFORM, "off_platform_or_unpaid_work"),
            (INJECTION, "prompt_injection"),
        )
        reasons = [reason for pattern, reason in rules if pattern.search(text)]
        return {
            "compliance": ComplianceVerdict(allowed=not reasons, reasons=reasons),
            "events": ["local_draft_rules_checked"],
        }

    async def preview(self, state):
        digest = draft_digest(state["draft"])
        if self.marketplace:
            from agent.marketplace_port import ProposalWrite

            request = ProposalWrite(
                job_id=state["raw_job"]["provider_job_id"],
                text=state["draft"].text,
                screening_answers=state["draft"].screening_answers,
                bid_amount=state["price"].amount,
                idempotency_key=f"student-proposal:{state['run_id']}:{digest}",
            )
            result = await self.marketplace.proposal(request)
            expected = {**request.arguments(), "draft_digest": digest}
            if (
                result.get("arguments") != expected
                or result.get("connects_cost") != state["price"].connects
            ):
                raise ReviewRequired("Provider preview changed; regenerate the quote")
            return {
                "preview": WritePreview(
                    tool="submit_proposal",
                    arguments=expected,
                    connects_cost=result["connects_cost"],
                    idempotency_key=request.idempotency_key,
                ),
                "status": "awaiting_approval",
                "marketplace_provider": state["raw_job"].get("source"),
                "events": ["student_submission_previewed"],
            }
        return {
            "preview": WritePreview(
                tool="save_local_draft",
                connects_cost=0,
                idempotency_key=f"local:{state['run_id']}:{digest}",
                arguments={
                    "run_id": state["run_id"],
                    "draft_digest": digest,
                    "scope": "local_only",
                    "marketplace_policy": "not_supplied",
                },
            ),
            "status": "awaiting_approval",
            "events": ["local_draft_previewed"],
        }

    async def execute(self, state):
        preview = state["preview"]
        if self.marketplace:
            from agent.marketplace_port import ProposalWrite

            if state["approval"].action != "approve" or preview.tool != "submit_proposal":
                raise ReviewRequired("Simulator submission requires exact human approval")
            request = ProposalWrite(
                **{key: value for key, value in preview.arguments.items() if key != "draft_digest"},
                idempotency_key=preview.idempotency_key,
                dry_run=False,
            )
            if preview.arguments.get("draft_digest") != draft_digest(state["draft"]):
                raise ReviewRequired("Proposal changed after approval")
            for item in state.get("evidence", []):
                await self.portfolio.read(item.id)
            result = await self.marketplace.proposal(request)
            if state["raw_job"].get("source") == "upwork":
                if result.get("status") != "pending_provider_confirmation":
                    raise ReviewRequired(
                        "Upwork preparation has no verified pending-confirmation result"
                    )
                return {
                    "status": "pending_provider_confirmation",
                    "provider_result": result,
                    "events": ["upwork_preview_prepared_not_submitted"],
                }
            return {"status": "submitted", "events": ["student_proposal_submitted"]}
        if state["approval"].action != "approve" or preview.tool != "save_local_draft":
            raise ReviewRequired("Only an explicitly approved local draft can be saved")
        if preview.arguments.get("draft_digest") != draft_digest(state["draft"]):
            raise ReviewRequired("The draft changed after its preview; request approval again")
        for item in state.get("evidence", []):
            await self.portfolio.read(item.id)
        # Host transaction must recheck ownership, approval and evidence, then perform
        # an idempotent local save. No provider capability is passed to these nodes.
        await self.execute_local(state)
        return {"status": "drafted", "events": ["local_draft_saved"]}
