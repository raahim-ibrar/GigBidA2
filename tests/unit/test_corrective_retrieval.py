from rag.retrieval import RetrievalContext
from rag.variants.v8_corrective import retrieve


def test_corrective_graph_requeries_weak_evidence_and_stops_when_supported():
    context = RetrievalContext(
        texts={"weak": "Brochure design", "strong": "FastAPI service"},
        dense=lambda query, k: (
            [("weak", 1.0)] if query == "Async request processing" else [("strong", 1.0)]
        ),
        rerank=lambda query, texts: [8.0 if "FastAPI" in text else -10.0 for text in texts],
    )
    found = retrieve("Async request processing", context=context)
    assert found == [("strong", 8.0)]
    assert 1 < len(context.queries) <= 3


def test_corrective_graph_abstains_after_its_query_budget():
    context = RetrievalContext(
        texts={"weak": "Brochure design"},
        dense=lambda query, k: [("weak", 1.0)],
        rerank=lambda query, texts: [-10.0] * len(texts),
    )
    assert retrieve("Underwater excavation certification", context=context) == []
    assert len(context.queries) == 3
