"""Metrics over explicit observations. Missing measurements never become successes."""

import math
from collections import Counter


def classification(gold, predicted):
    if not gold or len(gold) != len(predicted):
        raise ValueError("Nonempty, aligned labels are required")
    if any(type(value) is not bool for value in [*gold, *predicted]):
        raise ValueError("Labels must be booleans")
    counts = Counter((a, b) for a, b in zip(gold, predicted, strict=True))
    tp, fp, fn, tn = (
        counts[True, True],
        counts[False, True],
        counts[True, False],
        counts[False, False],
    )
    return {
        "n": len(gold),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "accuracy": (tp + tn) / len(gold),
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
    }


def retrieval(relevant, ranked, k):
    if k < 1 or len(ranked) != len(set(ranked)):
        raise ValueError("Positive k and unique ranked evidence IDs are required")
    relevant, top = set(relevant), ranked[:k]
    hits = [index for index, id in enumerate(top) if id in relevant]
    dcg = sum(1 / math.log2(index + 2) for index in hits)
    ideal = sum(1 / math.log2(index + 2) for index in range(min(len(relevant), k)))
    return {
        "recall": len(hits) / len(relevant) if relevant else None,
        "precision": len(hits) / k,
        "mrr": 1 / (hits[0] + 1) if hits else 0,
        "ndcg": dcg / ideal if ideal else None,
        "retrieved": len(top),
        "answerable": bool(relevant),
    }


def cohen_kappa(first, second):
    measured = classification(first, second)
    n = len(first)
    a, b = sum(first) / n, sum(second) / n
    expected = a * b + (1 - a) * (1 - b)
    return {
        "n": n,
        "agreement": measured["accuracy"],
        "expected_agreement": expected,
        "kappa": (measured["accuracy"] - expected) / (1 - expected) if expected < 1 else None,
    }
