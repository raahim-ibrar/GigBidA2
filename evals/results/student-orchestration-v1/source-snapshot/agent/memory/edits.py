"""Deterministic, bounded style candidates derived from actual cover-letter edits."""

import difflib
import re

STYLE_RULES = {
    "cut_opening": "Remove the opening sentence when the proposal remains coherent.",
    "concise": "Keep cover letters concise and avoid unnecessary wording.",
    "avoid_passionate": "Avoid the word ‘passionate’.",
    "avoid_excited": "Avoid the word ‘excited’.",
    "avoid_thrilled": "Avoid the word ‘thrilled’.",
}


def normalize(value):
    return re.sub(r"\s+", " ", value).strip().casefold()


def edit_observation(before: str, after: str):
    before_words, after_words = (
        re.findall(r"\b\w+\b", before.lower()),
        re.findall(r"\b\w+\b", after.lower()),
    )
    patterns = []
    if len(before_words) >= 10 and len(after_words) <= len(before_words) * 0.7:
        patterns.append("concise")
    parts = re.split(r"(?<=[.!?])\s+|\n+", before.strip(), maxsplit=1)
    if len(parts) == 2 and normalize(parts[1]) == normalize(after):
        patterns.append("cut_opening")
    for word in ("passionate", "excited", "thrilled"):
        if word in before_words and word not in after_words:
            patterns.append(f"avoid_{word}")
    diff = "\n".join(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile="reviewed",
            tofile="edited",
            lineterm="",
        )
    )
    return patterns, diff
