"""Real StateGraph topology with injected business nodes, currently unimplemented by default."""

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from agent.graphs.common import approval_gate, bid_approval_route, blocked, missing_node
from agent.state import BidState

BUSINESS_NODES = (
    "scout",
    "analyst",
    "risk",
    "matcher",
    "decision",
    "pricing",
    "writer",
    "verifier",
    "critic",
    "compliance",
    "preview",
    "execute",
)


def analysis_fanout(state):
    # Each branch reads the raw post. Matcher can decompose requirements independently;
    # it must not assume the parallel Analyst has already produced JobSpec.
    return [Send(name, dict(state)) for name in ("analyst", "risk", "matcher")]


def decision_route(state):
    return "pricing" if state["decision"].action == "bid" else "stop"


def critic_route(state, limit=2):
    if state["critique"].verdict == "pass":
        return "compliance"
    if state.get("user_edited"):
        # Keep the user's words. A failed critique needs another explicit user edit.
        return "attention"
    return "revise" if state.get("revisions", 0) < limit else "attention"


def revise(state):
    return {"revisions": state.get("revisions", 0) + 1}


def attention(state):
    return {"status": "needs_attention"}


def stop(state):
    return {"status": state["decision"].action}


def build_bid_graph(*, checkpointer, nodes=None, max_revisions=2):
    if checkpointer is None:
        raise ValueError("Provide a Postgres checkpointer; tests may use InMemorySaver")
    if not 0 <= max_revisions <= 2:
        raise ValueError("Critic revisions must be between zero and two")
    nodes = nodes or {}
    graph = StateGraph(BidState)
    for name in BUSINESS_NODES:
        graph.add_node(name, nodes.get(name, missing_node(name)))
    for name, node in {
        "approval": approval_gate,
        "revise": revise,
        "attention": attention,
        "stop": stop,
        "blocked": blocked,
    }.items():
        graph.add_node(name, node)
    graph.add_edge(START, "scout")
    graph.add_conditional_edges("scout", analysis_fanout, ["analyst", "risk", "matcher"])
    graph.add_edge(["analyst", "risk", "matcher"], "decision")
    graph.add_conditional_edges("decision", decision_route, {"pricing": "pricing", "stop": "stop"})
    for source, target in (
        ("pricing", "writer"),
        ("writer", "verifier"),
        ("verifier", "critic"),
        ("revise", "writer"),
        ("preview", "approval"),
    ):
        graph.add_edge(source, target)
    graph.add_conditional_edges(
        "critic",
        lambda state: critic_route(state, max_revisions),
        {
            "compliance": "compliance",
            "revise": "revise",
            "attention": "attention",
        },
    )
    graph.add_conditional_edges(
        "compliance",
        lambda s: s["compliance"].allowed,
        {
            True: "preview",
            False: "blocked",
        },
    )
    graph.add_conditional_edges(
        "approval", bid_approval_route, {"execute": "execute", "edit": "verifier", "stop": END}
    )
    for name in ("execute", "blocked", "attention", "stop"):
        graph.add_edge(name, END)
    return graph.compile(checkpointer=checkpointer)
