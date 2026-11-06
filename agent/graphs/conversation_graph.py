"""Conversation topology. Liaison, compliance, preview and execution need implementations."""

from langgraph.graph import END, START, StateGraph

from agent.graphs.common import approval_gate, bid_approval_route, blocked, missing_node
from agent.state import ConversationState


def build_conversation_graph(*, checkpointer, nodes=None):
    if checkpointer is None:
        raise ValueError("A durable checkpointer is required")
    nodes = nodes or {}
    graph = StateGraph(ConversationState)
    for name in ("intake", "liaison", "verifier", "compliance", "preview", "execute"):
        graph.add_node(name, nodes.get(name, missing_node(name)))
    graph.add_node("approval", approval_gate)
    graph.add_node("blocked", blocked)
    graph.add_edge(START, "intake")
    graph.add_conditional_edges(
        "intake", lambda state: state.get("intent") == "scam", {True: "blocked", False: "liaison"}
    )
    graph.add_conditional_edges(
        "liaison", lambda state: state.get("intent") == "scam", {True: "blocked", False: "verifier"}
    )
    graph.add_edge("verifier", "compliance")
    graph.add_conditional_edges(
        "compliance",
        lambda s: s["compliance"].allowed,
        {
            True: "preview",
            False: "blocked",
        },
    )
    graph.add_edge("preview", "approval")
    graph.add_conditional_edges(
        "approval", bid_approval_route, {"execute": "execute", "edit": "verifier", "stop": END}
    )
    graph.add_edge("execute", END)
    graph.add_edge("blocked", END)
    return graph.compile(checkpointer=checkpointer)
