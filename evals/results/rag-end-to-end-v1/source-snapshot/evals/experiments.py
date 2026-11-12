"""Predeclared stratified assignments and conservative A/B analysis for X2.

Assignment must happen before any outcomes are inspected. No provider is called.
"""

import hashlib
import math
import random
from collections import defaultdict
from fractions import Fraction


def assign_arms(jobs, seed):
    if not jobs or len({item["id"] for item in jobs}) != len(jobs):
        raise ValueError("Nonempty, unique experiment jobs are required")
    groups = defaultdict(list)
    for item in jobs:
        groups[(item["persona"], item["category"])].append(item["id"])
    assigned = {}
    for stratum, ids in sorted(groups.items()):
        digest = hashlib.sha256(f"{seed}:{stratum!r}".encode()).digest()
        rng = random.Random(int.from_bytes(digest, "big"))
        ordered = sorted(ids)
        rng.shuffle(ordered)
        offset = rng.randrange(2)
        for index, id in enumerate(ordered):
            assigned[id] = "evidence_first" if (index + offset) % 2 == 0 else "problem_first"
    return assigned


def fisher_exact(a_replies, a_n, b_replies, b_n):
    """Two-sided fixed-margin Fisher test, including tables no likelier than observed."""
    if any(type(value) is not int for value in (a_replies, a_n, b_replies, b_n)):
        raise ValueError("Reply counts must be integers")
    if not (0 <= a_replies <= a_n and 0 <= b_replies <= b_n and a_n > 0 and b_n > 0):
        raise ValueError("Both arms need valid observed counts")
    if a_n + b_n > 5000:
        raise ValueError("Use a reviewed large-sample implementation above 5000 observations")
    successes, total = a_replies + b_replies, a_n + b_n
    denominator = math.comb(total, a_n)

    def weight(a):
        return math.comb(successes, a) * math.comb(total - successes, a_n - a)

    observed = weight(a_replies)
    numerator = sum(
        value
        for a in range(max(0, a_n - (total - successes)), min(a_n, successes) + 1)
        if (value := weight(a)) <= observed
    )
    return float(Fraction(numerator, denominator))


def analyse_arms(assignments, observations, alpha=0.05):
    if not 0 < alpha < 1:
        raise ValueError("Alpha must lie strictly between 0 and 1")
    if not assignments or set(assignments) != {item["id"] for item in observations}:
        raise ValueError("Every assigned job needs a completed follow-up observation")
    if len(observations) != len(assignments):
        raise ValueError("Duplicate observations are not allowed")
    counts = {"evidence_first": [0, 0], "problem_first": [0, 0]}
    for item in observations:
        arm = assignments[item["id"]]
        if (
            arm not in counts
            or type(item["replied"]) is not bool
            or item.get("followup_complete") is not True
        ):
            raise ValueError(
                "Known arms, boolean replies and complete equal-window follow-up are required"
            )
        counts[arm][0] += item["replied"]
        counts[arm][1] += 1
    a, an = counts["evidence_first"]
    b, bn = counts["problem_first"]
    p = fisher_exact(a, an, b, bn)
    difference = a / an - b / bn
    # Hoeffding gives P(|p_hat-p| > e) <= 2 exp(-2 n e^2).
    # Allocate alpha/2 to each arm and use a union bound. The resulting interval
    # for the difference is intentionally conservative, rather than a Wald interval.
    radius = math.sqrt(math.log(4 / alpha) / (2 * an)) + math.sqrt(math.log(4 / alpha) / (2 * bn))
    return {
        "arms": {
            arm: {"replies": value[0], "n": value[1], "reply_rate": value[0] / value[1]}
            for arm, value in counts.items()
        },
        "difference_evidence_minus_problem": difference,
        "fisher_two_sided_p": p,
        "alpha": alpha,
        "difference_interval": [max(-1, difference - radius), min(1, difference + radius)],
        "interval_method": "Hoeffding union-bound; conservative independent-observation interval",
        "randomization_warning": "Pooled Fisher test is unadjusted for strata; "
        "inspect per-stratum effects. "
        "Repeated clients or interacting jobs violate independence assumptions.",
    }
