"""V1: retrieve each newline/semicolon-separated requirement, then reciprocal-rank fuse."""

from rag.retrieval import fuse, requirements


def retrieve(query, *, context, k=5):
    parts = requirements(query)
    context.queries.extend(parts)
    return fuse([context.dense(part, k) for part in parts], k)
