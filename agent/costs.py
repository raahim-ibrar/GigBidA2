"""Versioned standard-price estimates; never infer a provider invoice from tokens."""

import json
from decimal import Decimal
from pathlib import Path

from agent.handoffs import Contract

CATALOGUE = json.loads(Path(__file__).with_name("cost_rates.json").read_text(encoding="utf-8"))
RATES = {(r["provider"], r["model"]): r for r in CATALOGUE["rates"]}


def valid_tokens(metrics):
    return metrics.get("usage_known", True) is not False and all(
        type(metrics.get(k)) is int and metrics[k] >= 0 for k in ("input_tokens", "output_tokens")
    )


def priced_usage(metrics):
    """Snapshot rates onto a new usage event. No later repricing of that event."""
    data = {**metrics, "cost_version": CATALOGUE["version"], "estimated_usd": None}
    provider, model = metrics.get("provider"), metrics.get("model")
    if provider == "ollama":
        return {
            **data,
            "usd": 0.0,
            "estimated_usd": 0.0,
            "cost_status": "local_api_only",
            "cost_basis": "local inference; hardware and electricity excluded",
        }
    data.update(
        usd=None,
        cost_status="unknown_usage" if not valid_tokens(data) else "unknown_rate",
        cost_basis="Actual billing unverified; no complete price estimate available",
    )
    rate = RATES.get((provider, model))
    if not rate or not valid_tokens(data):
        return data
    input_rate, output_rate = (
        Decimal(rate["input_per_million"]),
        Decimal(rate["output_per_million"]),
    )
    amount = (
        Decimal(data["input_tokens"]) * input_rate + Decimal(data["output_tokens"]) * output_rate
    ) / Decimal(1000000)
    return {
        **data,
        "estimated_usd": float(amount),
        "cost_status": "list_price_estimate",
        "input_usd_per_million": str(input_rate),
        "output_usd_per_million": str(output_rate),
        "rate_checked_on": CATALOGUE["checked_on"],
        "rate_source": rate["source"],
        "cost_basis": "Standard uncached text list-price estimate, not an invoice; "
        "free-tier charges may be zero. Discounts, taxes, tools and infrastructure excluded.",
    }


class CostGroup(Contract):
    provider: str
    model: str
    role: str
    calls: int
    input_tokens: int
    output_tokens: int
    estimated_usd: float | None
    unknown_cost_calls: int


class CostSummary(Contract):
    currency: str = "USD"
    calls: int
    input_tokens: int
    output_tokens: int
    estimated_usd: float | None
    actual_api_usd: float | None
    unknown_cost_calls: int
    unaccounted_tokens: int
    complete: bool
    groups: list[CostGroup]
    basis: str = (
        "Recorded standard list-price subtotal, not actual billing. "
        "Free-tier charges may be zero; local hardware/electricity excluded. "
        "Unknown usage and reservations are not priced."
    )


def money(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    amount = Decimal(str(value))
    return amount if amount.is_finite() and amount >= 0 else None


def cost_summary(metrics, *, charged_tokens=0, active=False):
    groups, estimates, actuals = {}, [], []
    inputs = outputs = unknown = 0
    usage_complete = True
    for data in metrics:
        # Do not apply today's prices retrospectively to older usage records.
        estimate = money(data.get("estimated_usd"))
        if estimate is None and data.get("provider") == "ollama":
            estimate = Decimal(0)
        actual = money(data.get("usd"))
        measured = valid_tokens(data)
        usage_complete = usage_complete and measured
        incoming, outgoing = (data["input_tokens"], data["output_tokens"]) if measured else (0, 0)
        inputs, outputs = inputs + incoming, outputs + outgoing
        known = estimate is not None
        unknown += not known
        if known:
            estimates.append(estimate)
        if actual is not None:
            actuals.append(actual)
        key = tuple(str(data.get(k) or "unknown") for k in ("provider", "model", "role"))
        group = groups.setdefault(
            key, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "estimates": [], "unknown": 0}
        )
        group["calls"] += 1
        group["input_tokens"] += incoming
        group["output_tokens"] += outgoing
        group["unknown"] += not known
        if known:
            group["estimates"].append(estimate)
    count = sum(g["calls"] for g in groups.values())
    gap = max(0, charged_tokens - inputs - outputs)
    return CostSummary(
        calls=count,
        input_tokens=inputs,
        output_tokens=outputs,
        estimated_usd=float(sum(estimates)) if estimates else None,
        actual_api_usd=float(sum(actuals)) if count and len(actuals) == count and not gap else None,
        unknown_cost_calls=unknown,
        unaccounted_tokens=gap,
        complete=bool(count) and not unknown and not gap and not active and usage_complete,
        groups=[
            CostGroup(
                provider=k[0],
                model=k[1],
                role=k[2],
                calls=g["calls"],
                input_tokens=g["input_tokens"],
                output_tokens=g["output_tokens"],
                estimated_usd=float(sum(g["estimates"])) if g["estimates"] else None,
                unknown_cost_calls=g["unknown"],
            )
            for k, g in sorted(groups.items())
        ],
    )
