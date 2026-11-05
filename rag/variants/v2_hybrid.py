"""V2: lexical BM25L and dense candidates, with reciprocal-rank fusion."""

from rag.index.bm25 import rank
from rag.retrieval import fuse


def retrieve(query, *, context, k=5):
    context.queries.append(query)
    return fuse([rank(query, context.texts, k * 4), context.dense(query, k * 4)], k)
