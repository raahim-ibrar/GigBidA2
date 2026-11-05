import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

Ranking = list[tuple[str, float]]


@dataclass
class RetrievalContext:
    texts: dict[str, str]
    dense: Callable[[str, int], Ranking]
    rerank: Callable[[str, list[str]], list[float]]
    correction_threshold: float = 0.0
    max_corrections: int = 2
    queries: list[str] = field(default_factory=list)


def fuse(rankings: list[Ranking], k: int) -> Ranking:
    scores = defaultdict(float)
    for ranking in rankings:
        for rank, (id, _) in enumerate(ranking, 1):
            scores[id] += 1 / (60 + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:k]


def requirements(query: str) -> list[str]:
    pieces = [re.sub(r"^[-*\d.\s]+", "", part).strip() for part in re.split(r"[\n;]+", query)]
    return list(dict.fromkeys(p for p in pieces if p))[:12] or [query]
