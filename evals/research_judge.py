"""Independent free-model judge, frozen before human answers are read."""

import argparse
import asyncio
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from typing import Literal

import httpx
from dotenv import dotenv_values
from pydantic import BaseModel, Field

from agent.proposal_nodes import sentences

MODEL = "nvidia/nemotron-3.5-lightning:free"
PROMPT = Path("agent/prompts/experiments/proposal_quality_judge.md").read_text(encoding="utf-8")


class Label(BaseModel):
    index: int = Field(ge=0)
    label: Literal["supported", "unsupported", "not_factual"]
    reason: str


class Assessment(BaseModel):
    id: str
    quality: int = Field(ge=1, le=5)
    labels: list[Label]


class Batch(BaseModel):
    items: list[Assessment]


def validate_batch(inputs, result):
    expected = {item["id"]: {c["index"] for c in item["claims"]} for item in inputs}
    if len(result.items) != len(expected) or {r.id for r in result.items} != set(expected):
        raise ValueError("Judge must assess every supplied item exactly once")
    for row in result.items:
        if (
            len(row.labels) != len(expected[row.id])
            or {r.index for r in row.labels} != expected[row.id]
        ):
            raise ValueError("Judge must assess each claim exactly once")


async def predict(items, *, output, batch_size=5):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    plan = {
        "model": MODEL,
        "prompt": PROMPT,
        "temperature": 0,
        "seed": 4016,
        "batch_size": batch_size,
        "max_tokens": 5000,
        "output_protocol": "required native record_judgements function call",
        "schema_constraints": (
            "exact batch length, supplied item IDs, bounded claim indices; "
            "single-claim items require index zero"
        ),
        "items": items,
        "data_origin": "synthetic",
        "billing": "Only the fixed :free model; no paid fallback",
    }
    plan_path = output / "plan.json"
    if plan_path.exists() and json.loads(plan_path.read_text()) != plan:
        raise ValueError("Judge plan differs; preserve it and choose a new output directory")
    plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    raw_path, calls_path = output / "model-labels.jsonl", output / "calls.jsonl"
    done = (
        {json.loads(line)["id"] for line in raw_path.read_text().splitlines()}
        if raw_path.exists()
        else set()
    )
    pending = [item for item in items if item["id"] not in done]
    key = dotenv_values(".env").get("OPENROUTER_API_KEY")
    if not key:
        raise ValueError("Configure the ignored OPENROUTER_API_KEY")
    async with httpx.AsyncClient(timeout=180) as client:
        for start in range(0, len(pending), batch_size):
            group = pending[start : start + batch_size]
            schema = Batch.model_json_schema()
            schema["properties"]["items"].update(minItems=len(group), maxItems=len(group))
            schema["$defs"]["Assessment"]["properties"]["id"]["enum"] = [i["id"] for i in group]
            if all(len(i["claims"]) == 1 for i in group):
                schema["$defs"]["Label"]["properties"]["index"]["enum"] = [0]
                schema["$defs"]["Assessment"]["properties"]["labels"].update(minItems=1, maxItems=1)
            before = time.perf_counter()
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": "Bearer " + key},
                json={
                    "model": MODEL,
                    "temperature": 0,
                    "seed": 4016,
                    "max_tokens": 5000,
                    "reasoning": {"enabled": False},
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "record_judgements",
                                "description": (
                                    "Record all requested rubric scores and claim labels."
                                ),
                                "parameters": schema,
                            },
                        }
                    ],
                    "tool_choice": {"type": "function", "function": {"name": "record_judgements"}},
                    "messages": [
                        {"role": "system", "content": PROMPT},
                        {"role": "user", "content": json.dumps({"items": group})},
                    ],
                },
            )
            elapsed = time.perf_counter() - before
            if response.status_code != 200:
                raise RuntimeError(
                    f"Free judge unavailable (HTTP {response.status_code}); pending items retained"
                )
            body = response.json()
            record = {
                "ids": [i["id"] for i in group],
                "model": body.get("model"),
                "usage": body.get("usage"),
                "elapsed_seconds": elapsed,
                "finish_reason": body.get("choices", [{}])[0].get("finish_reason"),
                "response_id": body.get("id"),
            }
            with calls_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")
            if record["finish_reason"] != "tool_calls":
                raise ValueError("Judge output incomplete; no labels accepted")
            tool_calls = body["choices"][0]["message"].get("tool_calls", [])
            if len(tool_calls) != 1 or tool_calls[0]["function"]["name"] != "record_judgements":
                raise ValueError("Judge must call record_judgements exactly once")
            content = tool_calls[0]["function"]["arguments"]
            try:
                parsed = Batch.model_validate_json(content)
                validate_batch(group, parsed)
            except ValueError:
                (output / "invalid-response.txt").write_text(content, encoding="utf-8")
                raise
            with raw_path.open("a", encoding="utf-8") as handle:
                for item in parsed.items:
                    handle.write(item.model_dump_json() + "\n")
            print(f"Judge: recorded {len(group)} items, {elapsed:.1f}s", flush=True)
            await asyncio.sleep(max(0, 3.2 - elapsed))


def categorical_agreement(first, second, categories, *, weighted=False):
    if not first or len(first) != len(second) or any(x not in categories for x in first + second):
        raise ValueError("Aligned nonempty labels from the declared categories are required")
    n = len(first)
    counts, a, b = Counter(zip(first, second, strict=True)), Counter(first), Counter(second)

    def weight(x, y):
        return (
            ((categories.index(x) - categories.index(y)) / (len(categories) - 1)) ** 2
            if weighted
            else float(x != y)
        )

    observed = sum(weight(x, y) * count / n for (x, y), count in counts.items())
    expected = sum(weight(x, y) * a[x] * b[y] / n**2 for x in categories for y in categories)
    return {
        "n": n,
        "agreement": sum(x == y for x, y in zip(first, second, strict=True)) / n,
        "kappa": 1 - observed / expected if expected else None,
        "method": "quadratic weighted Cohen kappa" if weighted else "Cohen kappa",
    }


def analyse_calibration(human_path, judge_path, packet_path, output):
    human = json.loads(Path(human_path).read_text())
    packet = json.loads(Path(packet_path).read_text())
    if not human.get("complete") or human["packet_id"] != packet["packet_id"]:
        raise ValueError("A complete human response to the frozen packet is required")
    expected = {item["id"] for item in packet["items"]}
    humans = {r["id"]: r for r in human["ratings"]}
    judges = {r["id"]: r for r in map(json.loads, Path(judge_path).read_text().splitlines())}
    if set(humans) != expected or set(judges) != expected or len(human["ratings"]) != len(expected):
        raise ValueError("Every frozen item requires one human and one judge response")
    ids = sorted(expected)
    support = categorical_agreement(
        [humans[i]["support"] for i in ids],
        [judges[i]["labels"][0]["label"] for i in ids],
        ["supported", "unsupported", "not_factual"],
    )
    quality = categorical_agreement(
        [humans[i]["quality"] for i in ids],
        [judges[i]["quality"] for i in ids],
        [1, 2, 3, 4, 5],
        weighted=True,
    )
    result = {
        "packet_id": packet["packet_id"],
        "model": MODEL,
        "support": support,
        "quality": quality,
        "human_raters": 1,
        "data_origin": "synthetic",
        "limits": (
            "Single human, purpose-built calibration examples; "
            "agreement is not proof of correctness or transfer to real jobs"
        ),
        "human_response_sha256": hashlib.sha256(Path(human_path).read_bytes()).hexdigest(),
        "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
    }
    Path(output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def calibration_inputs():
    packet = json.loads(Path("output/reviews/calibration.json").read_text())
    return [
        {
            "id": row["id"],
            "job": row["job"],
            "evidence": row["evidence"],
            "proposal": row["proposal"],
            "claims": [{"index": 0, "text": row["claim"]}],
        }
        for row in packet["items"]
    ]


def proposal_inputs(path):
    return [
        {
            "id": row["id"] + ":" + row["condition"],
            "job": row["job"],
            "evidence": row["evidence"],
            "proposal": row["candidate"],
            "claims": [
                {"index": i, "text": text}
                for i, text in enumerate(
                    sentences(
                        row["candidate"]["text"]
                        + "\n"
                        + "\n".join(row["candidate"].get("screening_answers", {}).values())
                    )
                )
            ],
        }
        for row in map(json.loads, Path(path).read_text().splitlines())
        if row["candidate"].get("text")
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["calibration", "proposals", "analyse"])
    parser.add_argument("--input")
    parser.add_argument("--human")
    parser.add_argument("--output", default="evals/results/judge-calibration-v1")
    args = parser.parse_args()
    if args.mode == "analyse":
        print(
            json.dumps(
                analyse_calibration(
                    args.human, args.input, "output/reviews/calibration.json", args.output
                )
            )
        )
    else:
        items = calibration_inputs() if args.mode == "calibration" else proposal_inputs(args.input)
        asyncio.run(predict(items, output=args.output))
