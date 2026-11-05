"""Tests inject deterministic nodes. These are NOT GigSim or LLM outcome evaluations."""

from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agent.graphs.bid_graph import BUSINESS_NODES, build_bid_graph
from agent.graphs.conversation_graph import build_conversation_graph
from agent.handoffs import (
    BidDecision,
    ComplianceVerdict,
    Critique,
    FitReport,
    JobSpec,
    ProposalDraft,
    RiskReport,
    WritePreview,
)


def fixtures(*, action="bid", critic="pass", allowed=True):
    calls = []

    def make(name, update):
        async def node(state):
            calls.append(name)
            return {**update, "events": [name]}

        return node

    updates = {
        "scout": {},
        "analyst": {"job": JobSpec(job_id="fixture", title="Fixture", requirements=["Python"])},
        "risk": {"risk": RiskReport(score=0)},
        "matcher": {"fit": FitReport(score=1, requirement_evidence={})},
        "decision": {"decision": BidDecision(action=action, reasons=["Test fixture"])},
        "pricing": {},
        "writer": {"draft": ProposalDraft(text="Could we discuss your requirements?")},
        "verifier": {},
        "critic": {"critique": Critique(verdict=critic)},
        "compliance": {"compliance": ComplianceVerdict(allowed=allowed)},
        "preview": {
            "preview": WritePreview(
                tool="submit_proposal",
                arguments={},
                connects_cost=0,
                idempotency_key="fixture-key",
            )
        },
        "execute": {"status": "fixture_executed"},
    }
    return {name: make(name, updates[name]) for name in BUSINESS_NODES}, calls


def config():
    return {"configurable": {"thread_id": str(uuid4())}}


@pytest.mark.asyncio
async def test_parallel_branches_join_before_decision_and_pause():
    nodes, calls = fixtures()
    graph = build_bid_graph(checkpointer=InMemorySaver(), nodes=nodes)
    result = await graph.ainvoke({"events": []}, config())
    assert "__interrupt__" in result
    for branch in ("analyst", "risk", "matcher"):
        assert calls.index(branch) < calls.index("decision")
    assert calls.count("decision") == 1
    assert "execute" not in calls


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["approve", "reject", "edit"])
async def test_only_approve_reaches_executor(action):
    nodes, calls = fixtures()
    graph = build_bid_graph(checkpointer=InMemorySaver(), nodes=nodes)
    cfg = config()
    await graph.ainvoke({"events": []}, cfg)
    payload = {"action": action, "reason": "Not a fit", "edited_text": "An edited fixture"}
    result = await graph.ainvoke(Command(resume=payload), cfg)
    assert ("execute" in calls) == (action == "approve")
    if action == "edit":
        assert "__interrupt__" in result
        assert result["draft"].text == "An edited fixture"
        assert calls.count("verifier") == 2
        assert calls.count("compliance") == 2
    else:
        assert result["status"] == {"approve": "fixture_executed", "reject": "rejected"}[action]


@pytest.mark.asyncio
async def test_critic_exhaustion_stops_after_two_revisions():
    nodes, calls = fixtures(critic="revise")
    graph = build_bid_graph(checkpointer=InMemorySaver(), nodes=nodes)
    result = await graph.ainvoke({"events": []}, config())
    assert result["status"] == "needs_attention"
    assert calls.count("writer") == 3  # Initial draft plus two revisions.
    assert "execute" not in calls


@pytest.mark.asyncio
async def test_compliance_block_never_requests_approval():
    nodes, calls = fixtures(allowed=False)
    graph = build_bid_graph(checkpointer=InMemorySaver(), nodes=nodes)
    result = await graph.ainvoke({"events": []}, config())
    assert result["status"] == "blocked"
    assert "__interrupt__" not in result
    assert "execute" not in calls


@pytest.mark.asyncio
async def test_skip_never_drafts():
    nodes, calls = fixtures(action="skip")
    graph = build_bid_graph(checkpointer=InMemorySaver(), nodes=nodes)
    result = await graph.ainvoke({"events": []}, config())
    assert result["status"] == "skip"
    assert "writer" not in calls


@pytest.mark.asyncio
async def test_default_graph_cannot_pretend_to_process_jobs():
    graph = build_bid_graph(checkpointer=InMemorySaver())
    with pytest.raises(NotImplementedError, match="scout"):
        await graph.ainvoke({}, config())


@pytest.mark.asyncio
async def test_conversation_has_an_approval_interrupt():
    nodes, calls = fixtures()
    nodes["liaison"] = nodes["writer"]
    graph = build_conversation_graph(checkpointer=InMemorySaver(), nodes=nodes)
    result = await graph.ainvoke({}, config())
    assert "__interrupt__" in result
    assert "execute" not in calls


def test_checkpointer_cannot_be_omitted():
    with pytest.raises(ValueError):
        build_bid_graph(checkpointer=None)


async def test_configured_zero_critic_revisions_stops_after_first_draft():
    nodes, calls = fixtures(critic="revise")
    graph = build_bid_graph(checkpointer=InMemorySaver(), nodes=nodes, max_revisions=0)
    result = await graph.ainvoke({"events": []}, config())
    assert result["status"] == "needs_attention" and calls.count("writer") == 1
