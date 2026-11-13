"""Actual native ReAct and langgraph-supervisor baselines over shared MCP capabilities."""

import json
from pathlib import Path
from typing import Literal

from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from langgraph_supervisor import create_supervisor
from pydantic import BaseModel, Field

from agent.handoffs import ProposalDraft
from agent.proposal_nodes import ProposalNodes
from agent.safety import EMAIL, GUARANTEE, INJECTION, OFF_PLATFORM, PHONE
from evals.research_client import native_model


def prompt_text(name):
    return (
        (Path(__file__).resolve().parents[1] / "agent/prompts/experiments" / name)
        .read_text(encoding="utf-8")
        .strip()
    )


class Candidate(BaseModel):
    action: Literal["bid", "watch", "skip"]
    risk_score: float = Field(ge=0, le=1)
    reasons: list[str] = Field(min_length=1, max_length=5)
    price: float | None = Field(default=None, gt=0)
    text: str = Field(default="", max_length=6000)
    screening_answers: dict[str, str] = Field(default_factory=dict)


class NativeResearchError(RuntimeError):
    def __init__(self, cause, usage, calls, candidate):
        super().__init__(type(cause).__name__)
        self.usage, self.calls, self.candidate = usage, calls, candidate
        self.cause = cause


def policy_violations(text):
    return [
        label
        for pattern, label in [
            (EMAIL, "contact_email"),
            (PHONE, "contact_phone"),
            (GUARANTEE, "unsupported_guarantee"),
            (OFF_PLATFORM, "off_platform_or_unpaid_work"),
            (INJECTION, "prompt_injection"),
        ]
        if pattern.search(text)
    ]


async def run_native(kind, settings, model, config, raw, portfolio, marketplace, strategy):
    usage, calls, holder = [], [], {}
    chat, client, budget = native_model(settings, model, usage)

    @tool
    async def get_job() -> dict:
        """Read the fixed current job from the account-bound Marketplace MCP."""
        calls.append("get_job")
        return await marketplace.job(raw["id"])

    @tool
    async def search_jobs(query: str) -> dict:
        """Search the research marketplace; the assigned current job remains fixed."""
        calls.append("search_jobs")
        return await marketplace.search(query, limit=5)

    @tool
    async def search_evidence(query: str) -> list[dict]:
        """Retrieve the persona's actual indexed portfolio evidence through MCP."""
        calls.append("search_evidence")
        return [e.model_dump() for e in await portfolio.search(query, k=3, variant="v3")]

    @tool
    async def read_evidence(evidence_id: str) -> dict:
        """Re-read a cited immutable portfolio source through MCP."""
        calls.append("read_evidence")
        return (await portfolio.read(evidence_id)).model_dump()

    @tool
    async def client_history() -> dict:
        """Read the simulator's generated client history, not real marketplace history."""
        calls.append("client_history")
        return await marketplace.client(raw["client_id"])

    @tool
    async def connects_balance() -> dict:
        """Read available simulated Connects for the account."""
        calls.append("connects_balance")
        return await marketplace.balance()

    @tool
    async def check_compliance(text: str) -> dict:
        """Check a proposed draft for contact details, payment pressure and prompt injection."""
        calls.append("check_compliance")
        problems = policy_violations(text)
        return {"allowed": not problems, "violations": problems}

    @tool
    async def verify_proposal(text: str) -> dict:
        """Verify sentence claims against retrieved evidence, returning a grounded revision."""
        from agent.providers.groq import GroqModels

        factory = GroqModels
        if config.profile.get("provider") == "gemini":
            from agent.providers.gemini import GeminiModels

            factory = GeminiModels

        calls.append("verify_proposal")
        evidence = await portfolio.search(raw["title"], k=3, variant="v3")

        async def record(row):
            usage.append(row)

        nodes = ProposalNodes(
            factory(
                "",
                config,
                record=record,
                reserve_budget=budget.reserve,
                settle_budget=budget.settle,
            ),
            portfolio,
            config,
            execute_local=lambda state: None,
        )
        checked = await nodes.verifier({"draft": ProposalDraft(text=text), "evidence": evidence})
        return {"draft": checked["draft"].model_dump(), "verification": checked["verification"]}

    @tool(args_schema=Candidate, return_direct=True)
    async def finalize_candidate(**kwargs) -> str:
        """Record the final research decision and candidate. Does not submit or approve anything."""
        calls.append("finalize_candidate")
        holder["candidate"] = Candidate.model_validate(kwargs)
        return "Research candidate recorded. Stop; no user approval or external action occurred."

    @tool(return_direct=True)
    async def report_analysis(summary: str) -> str:
        """Finish the analyst's work and return a concise assessment to the supervisor."""
        calls.append("report_analysis")
        return summary

    @tool(return_direct=True)
    async def finish_research() -> str:
        """Finish the supervisor workflow after the writer has recorded its candidate."""
        calls.append("finish_research")
        if "candidate" not in holder:
            raise ValueError("No candidate recorded; delegate to the writer first")
        return "Research workflow complete. No application was approved or sent."

    reads = [get_job, search_jobs, search_evidence, read_evidence, client_history, connects_balance]
    checks = [check_compliance, verify_proposal]
    prompt = prompt_text("native_bid.md").format(strategy=strategy)
    try:
        if kind == "react":
            app = create_react_agent(
                chat,
                [*reads, *checks, finalize_candidate],
                prompt=prompt,
                name="single_agent",
            )
        elif kind == "supervisor":
            analyst = create_react_agent(
                chat,
                [*reads, report_analysis],
                prompt=prompt + " " + prompt_text("native_analyst.md"),
                name="analyst",
            )
            writer = create_react_agent(
                chat,
                [*reads, *checks, finalize_candidate],
                prompt=prompt + " " + prompt_text("native_writer.md"),
                name="writer",
            )
            app = create_supervisor(
                [analyst, writer],
                model=chat,
                tools=[finish_research],
                output_mode="last_message",
                add_handoff_back_messages=False,
                prompt=prompt_text("native_supervisor.md"),
            ).compile()
        else:
            raise ValueError("Unknown native architecture")
        await app.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "assigned_job_id": raw["id"],
                                "title": raw["title"],
                                "strategy": strategy,
                            }
                        ),
                    }
                ]
            },
            {"recursion_limit": 30},
        )
        if "candidate" not in holder:
            raise ValueError("Agent stopped without a final research decision")
        return holder["candidate"], usage, calls
    except Exception as error:
        raise NativeResearchError(error, usage, calls, holder.get("candidate")) from error
    finally:
        await client.aclose()
