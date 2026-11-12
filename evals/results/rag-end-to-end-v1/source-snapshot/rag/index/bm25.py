import re

import numpy as np
from rank_bm25 import BM25L


def tokens(text: str) -> list[str]:
    return re.findall(r"[\w+#]+(?:[.-][\w+#]+)*", text.casefold())


def rank(query: str, items: dict[str, str], k: int):
    if not items:
        return []
    ids = list(items)
    # A zero-score BM25 hit is not evidence that a keyword matched.
    matrix = [tokens(items[id]) or [""] for id in ids]
    scores = BM25L(matrix).get_scores(tokens(query))
    order = np.argsort(-scores, kind="stable")
    return [(ids[i], float(scores[i])) for i in order[:k] if scores[i] > 0]
