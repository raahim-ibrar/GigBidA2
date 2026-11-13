"""Deterministic USD posted-budget comparisons, never estimates of actual earnings."""

import math
import re
from statistics import median, quantiles


def positive(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


def summarize(values):
    result = {"count": len(values)}
    if len(values) >= 5:
        quartiles = quantiles(values, n=4, method="inclusive")
        result.update(median=median(values), p25=quartiles[0], p75=quartiles[2])
    return result


def budget_statistics(job, records, *, provider):
    """Exclude self/duplicates, currencies, billing units and unrelated skills.

    Client IDs in the simulator are fictional. Never join them to live clients.
    Archived posting budgets and generated budgets are separate cohorts.
    """
    skills = {
        s.casefold()
        for s in job.get("required_skills", job.get("skills", []))
        if isinstance(s, str)
    }
    text = (job.get("title", "") + " " + job.get("description", "")).casefold()
    cohorts = {"historical_posted_budgets": [], "synthetic_posted_budgets": []}
    clients = {key: [] for key in cohorts}
    seen = set()
    for row in records:
        identity = row.get("id")
        if not identity or identity == job.get("id") or identity in seen:
            continue
        seen.add(identity)
        if row.get("currency") != "USD" or row.get("billing_type") != job.get("billing_type"):
            continue
        other = {s.casefold() for s in row.get("required_skills", []) if isinstance(s, str)}
        matched = skills | {
            s for s in other if re.search(r"(?<!\w)" + re.escape(s) + r"(?!\w)", text)
        }
        # A generic shared skill alone is not a comparable project.
        if len(matched & other) < 2:
            continue
        low, high = row.get("budget_min"), row.get("budget_max")
        if not positive(high) or (low is not None and (not positive(low) or low > high)):
            continue
        value = ((low or high) + high) / 2
        provenance = row.get("provenance")
        historical = (
            isinstance(provenance, dict) and provenance.get("base_text") == "real_historical_job"
        )
        cohort = "historical_posted_budgets" if historical else "synthetic_posted_budgets"
        if not historical and row.get("synthetic") is not True:
            continue  # Unknown provenance is not market evidence.
        cohorts[cohort].append(value)
        if (
            provider == "student_sim"
            and job.get("client_id")
            and row.get("client_id") == job["client_id"]
        ):
            clients[cohort].append(value)
    source = "historical_posted_budgets"
    if len(cohorts[source]) < 5:
        source = "synthetic_posted_budgets"
    return {
        "currency": "USD",
        "billing_type": job.get("billing_type"),
        "market": {**summarize(cohorts[source]), "source": source},
        "client": {**summarize(clients[source]), "source": "synthetic_client_posted_budgets"},
        "limitations": "Selected comparable posting budget midpoints, not paid contract rates. "
        "Minimum five records; two shared skills. "
        "Client IDs and history are synthetic in the simulator. "
        "Archived market data may be stale and is not representative of all freelancers.",
    }


def reference_price(statistics, billing_type):
    """Use a robust median; cap client influence to 25% and the market IQR."""
    if statistics.get("currency") != "USD" or statistics.get("billing_type") != billing_type:
        return None, "No comparable USD statistics; using the entered budget."
    market, client = statistics.get("market", {}), statistics.get("client", {})
    if market.get("count", 0) < 5 or not all(
        positive(market.get(k)) for k in ("median", "p25", "p75")
    ):
        return None, "Fewer than five comparable market records; using the entered budget."
    value = market["median"]
    explanation = (
        f"{market.get('source')}: n={market['count']}, median ${value:.2f}, "
        f"IQR ${market['p25']:.2f}–${market['p75']:.2f}."
    )
    if client.get("count", 0) >= 5 and positive(client.get("median")):
        adjusted = min(max(client["median"], market["p25"]), market["p75"])
        value = 0.75 * value + 0.25 * adjusted
        explanation += (
            f" Client posted-budget history n={client['count']}, "
            f"median ${client['median']:.2f}; 25% weight, capped to market IQR "
            f"({client.get('source')})."
        )
    else:
        explanation += (
            " Comparable client price history unavailable or too sparse; no client uplift."
        )
    return value, explanation + " Budgets are not earnings; review scope before approval."
