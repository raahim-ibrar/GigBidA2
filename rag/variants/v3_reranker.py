"""V3: rerank a bounded hybrid candidate set with an open cross-encoder."""

from rag.variants.v2_hybrid import retrieve as hybrid


def retrieve(query, *, context, k=5):
    candidates = hybrid(query, context=context, k=min(80, k * 4))
    ids = [id for id, _ in candidates]
    scores = context.rerank(query, [context.texts[id] for id in ids])
    return sorted(zip(ids, scores, strict=True), key=lambda item: (-item[1], item[0]))[:k]
