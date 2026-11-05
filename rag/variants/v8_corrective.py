"""V8: a bounded LangGraph retrieve/grade/correct loop, with explicit abstention."""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from rag.retrieval import Ranking, requirements
from rag.variants.v3_reranker import retrieve as rerank


class CorrectiveState(TypedDict):
    candidates: Ranking
    accepted: dict[str, float]
    pending: list[str]
    attempts: int


def retrieve(query, *, context, k=5):
    parts = requirements(query)

    def initial(state):
        return {"candidates": rerank(query, context=context, k=k)}

    def grade(state):
        accepted = dict(state["accepted"])
        for id, score in state["candidates"]:
            if score >= context.correction_threshold:
                accepted[id] = max(accepted.get(id, float("-inf")), score)
        texts = [context.texts[id] for id in accepted]
        pending = []
        for part in parts:
            scores = context.rerank(part, texts)
            if not scores or max(scores) < context.correction_threshold:
                pending.append(part)
        return {"accepted": accepted, "pending": pending}

    def correction(state):
        pending = state["pending"] or parts
        part = pending[state["attempts"] % len(pending)]
        generic = {"need", "looking", "for", "developer", "experience", "with", "a", "an", "the"}
        focused = " ".join(word for word in part.split() if word.casefold() not in generic)[:1000]
        if not focused or focused in context.queries:
            focused = part + " project implementation"
        found = rerank(focused, context=context, k=k)
        ids = [id for id, _ in found]
        # Re-querying cannot authorize unrelated evidence: grade the original requirement.
        scores = context.rerank(part, [context.texts[id] for id in ids])
        return {
            "candidates": list(zip(ids, scores, strict=True)),
            "attempts": state["attempts"] + 1,
        }

    def route(state):
        weak = bool(state["pending"]) or not state["accepted"]
        return "correct" if weak and state["attempts"] < context.max_corrections else "finish"

    graph = StateGraph(CorrectiveState)
    graph.add_node("retrieve", initial)
    graph.add_node("grade", grade)
    graph.add_node("correct", correction)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "grade")
    graph.add_conditional_edges("grade", route, {"correct": "correct", "finish": END})
    graph.add_edge("correct", "grade")
    result = graph.compile().invoke(
        {"candidates": [], "accepted": {}, "pending": [], "attempts": 0}
    )
    return sorted(result["accepted"].items(), key=lambda item: (-item[1], item[0]))[:k]
