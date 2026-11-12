from collections import defaultdict

from evals.io import align
from evals.metrics import classification, retrieval


def rag_scores(gold, predictions, k=5):
    rows = align(gold, predictions)
    groups = defaultdict(list)
    for truth, predicted in rows:
        if predicted.ranked_ids is None:
            raise ValueError(f"Missing ranked retrieval output for {truth.id}")
        groups[truth.persona].append(retrieval(truth.relevant_ids, predicted.ranked_ids, k))

    def summarize(items):
        answerable = [item for item in items if item["answerable"]]
        return {
            "n": len(items),
            "answerable": len(answerable),
            "unanswerable": len(items) - len(answerable),
            "macro_recall_at_k": sum(item["recall"] for item in answerable) / len(answerable)
            if answerable
            else None,
            "macro_mrr_at_k": sum(item["mrr"] for item in answerable) / len(answerable)
            if answerable
            else None,
            "macro_ndcg_at_k": sum(item["ndcg"] for item in answerable) / len(answerable)
            if answerable
            else None,
            "macro_precision_at_k": sum(item["precision"] for item in items) / len(items),
            "unanswerable_with_retrieval": sum(
                not item["answerable"] and item["retrieved"] > 0 for item in items
            ),
        }

    return {
        "k": k,
        "overall": summarize([item for items in groups.values() for item in items]),
        "by_persona": {key: summarize(items) for key, items in sorted(groups.items())},
    }


def decision_scores(gold, predictions):
    rows = align(gold, predictions)
    if any(item.bid is None or item.scam is None for _, item in rows):
        raise ValueError("Every prediction needs a bid and scam decision")
    groups = defaultdict(list)
    for truth, predicted in rows:
        groups[truth.persona].append((truth, predicted))

    def summarize(items):
        bands = [(a, b) for a, b in items if a.price_min is not None]
        annotations = [b for _, b in items if b.claim_labels is not None]
        labels = [label for item in annotations for label in item.claim_labels]
        complete = len(annotations) == len(items)
        return {
            "bid": classification([a.bid for a, _ in items], [b.bid for _, b in items]),
            "scam": classification([a.scam for a, _ in items], [b.scam for _, b in items]),
            "price_band_n": len(bands),
            "price_in_band_rate": sum(
                b.price is not None and a.price_min <= b.price <= a.price_max for a, b in bands
            )
            / len(bands)
            if bands
            else None,
            "claim_annotated_jobs": len(annotations),
            "claim_annotations_complete": complete,
            "labelled_claims": len(labels),
            "unsupported_claim_rate": sum(label != "supported" for label in labels) / len(labels)
            if labels and complete
            else None,
        }

    return {
        "overall": summarize(rows),
        "by_persona": {key: summarize(items) for key, items in sorted(groups.items())},
    }
