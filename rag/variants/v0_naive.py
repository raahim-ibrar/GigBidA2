"""V0: fixed chunks, whole-query dense cosine search."""


def retrieve(query, *, context, k=5):
    context.queries.append(query)
    return context.dense(query, k)
