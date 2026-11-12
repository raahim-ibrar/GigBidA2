"""Blinded, offline-capable human review packets. No labels are supplied by the agent."""

import argparse
import hashlib
import json
import random
from pathlib import Path

from scripts.student_personas import TOPICS

ROOT = Path(__file__).resolve().parents[1]


def calibration_items():
    items = []
    for persona, topics in TOPICS.items():
        for i in range(10):
            title, skills, goal, method = topics[i % len(topics)]
            evidence = (
                f"Fictional coursework portfolio: {title}. "
                f"I used {', '.join(skills)} to {method}. "
                "I documented acceptance criteria, checked malformed inputs and supplied "
                "reproducible tests and a handover guide. This was a scoped demonstration, "
                "not paid client work or a production deployment. No business uplift, "
                "accuracy number, years of experience or client testimonial is established."
            )
            claims = [
                f"In a coursework demonstration, I used {', '.join(skills)} to {method}.",
                "My previous deployment increased the client's revenue by 37%.",
                "I would start by confirming the inputs and acceptance criteria with you.",
                "I supplied reproducible tests and a handover guide for a scoped demonstration.",
                "I have extensive production experience operating Kubernetes on AWS.",
                "I would validate malformed inputs and document the handover steps.",
                "I delivered this project to paying clients as a production service.",
                f"My {title} coursework prototype included documented acceptance criteria.",
                "I have ten years of professional experience with this exact workflow.",
                "Could you share a sample input and clarify the desired output format?",
            ]
            claim = claims[i]
            items.append(
                {
                    "id": f"cal-{persona}-{i:02d}",
                    "job": f"Help a team {goal}; include validation, tests and a handover.",
                    "evidence": evidence,
                    "claim": claim,
                    "proposal": (
                        f"I understand you need to {goal}. {claim} "
                        "My proposed first step is to agree on sample inputs and acceptance "
                        "criteria, then implement a small reproducible solution with tests."
                    ),
                }
            )
    random.Random(4016).shuffle(items)
    return items


def panel_items():
    directory = ROOT / "evals/results/student-generation-v3"
    a = {
        row["id"]: row
        for row in map(json.loads, (directory / "qwen3.5-4b.jsonl").read_text().splitlines())
    }
    b = {
        row["id"]: row
        for row in map(json.loads, (directory / "qwen3-8b.jsonl").read_text().splitlines())
    }
    rng, selected, key = random.Random(4016), [], {}
    for persona in TOPICS:
        eligible = [
            identity
            for identity in sorted(set(a) & set(b))
            if a[identity]["persona"] == persona
            and a[identity]["snapshot"].get("draft")
            and b[identity]["snapshot"].get("draft")
        ]
        rng.shuffle(eligible)
        for identity in eligible[:4]:
            pair_id = "pair-" + hashlib.sha256(identity.encode()).hexdigest()[:10]
            order = [a[identity], b[identity]]
            rng.shuffle(order)
            sources = {
                evidence["id"]: evidence
                for row in order
                for evidence in row["snapshot"].get("evidence", [])
            }
            selected.append(
                {
                    "id": pair_id,
                    "job": order[0]["snapshot"]["job"],
                    "evidence": [
                        {"source": source["source"], "text": source["text"]}
                        for source in sources.values()
                    ],
                    "a": order[0]["snapshot"]["draft"],
                    "b": order[1]["snapshot"]["draft"],
                }
            )
            key[pair_id] = {
                "job_id": identity,
                "a": "qwen3.5-4b" if order[0] is a[identity] else "qwen3-8b",
                "b": "qwen3.5-4b" if order[1] is a[identity] else "qwen3-8b",
            }
    rng.shuffle(selected)
    return selected, key


def write_packets(output="output/reviews"):
    output = ROOT / output
    output.mkdir(parents=True, exist_ok=True)
    private = ROOT / "work/human-review"
    private.mkdir(parents=True, exist_ok=True)
    pairs, key = panel_items()
    specs = {
        "calibration": {
            "kind": "calibration",
            "title": "Judge calibration · 30 human labels",
            "items": calibration_items(),
            "origin": "Purpose-built fictional calibration examples; not final evaluation jobs",
        },
        "panel": {
            "kind": "panel",
            "title": "Blind proposal review · 12 pairs",
            "items": pairs,
            "origin": (
                "Actual raw candidates from the frozen local-model baseline, including "
                "drafts that failed the application's verification. All portfolios are fictional. "
                "This panel evaluates raw generation, not approved production proposals."
            ),
        },
    }
    template = (ROOT / "evals/review_template.html").read_text(encoding="utf-8")
    for name, spec in specs.items():
        digest = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()
        spec["packet_id"] = f"{name}-{digest[:16]}"
        blob = json.dumps(spec, ensure_ascii=True).replace("<", "\\u003c")
        (output / f"{name}.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
        (output / f"{name}.html").write_text(
            template.replace("__PACKET_JSON__", blob), encoding="utf-8"
        )
    (private / "panel-key.json").write_text(json.dumps(key, indent=2), encoding="utf-8")
    return {name: spec["packet_id"] for name, spec in specs.items()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="output/reviews")
    print(json.dumps(write_packets(parser.parse_args().output)))
