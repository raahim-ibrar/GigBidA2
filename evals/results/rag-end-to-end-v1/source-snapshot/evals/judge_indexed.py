"""Same independent rubric, exact keyed claim schema to prevent invented indices."""

import asyncio
import hashlib
import json
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values

from evals.research_judge import MODEL, PROMPT, Batch, proposal_inputs, validate_batch

ROOT = Path("evals/results/judge-proposals-v3")
SYSTEM = PROMPT


def keyed_schema(group):
    label = {
        "type": "object",
        "properties": {
            "index": {"type": "integer"},
            "label": {"type": "string", "enum": ["supported", "unsupported", "not_factual"]},
            "reason": {"type": "string"},
        },
        "required": ["index", "label", "reason"],
        "additionalProperties": False,
    }
    variants = []
    for item in group:
        indices = [c["index"] for c in item["claims"]]
        item_label = {
            **label,
            "properties": {**label["properties"], "index": {"type": "integer", "enum": indices}},
        }
        variants.append(
            {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "enum": [item["id"]]},
                    "quality": {"type": "integer", "minimum": 1, "maximum": 5},
                    "labels": {
                        "type": "array",
                        "items": item_label,
                        "minItems": len(indices),
                        "maxItems": len(indices),
                    },
                },
                "required": ["id", "quality", "labels"],
                "additionalProperties": False,
            }
        )
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {"anyOf": variants},
                "minItems": len(group),
                "maxItems": len(group),
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }


async def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    items = proposal_inputs("evals/results/gemini-orchestration-v1/runs.jsonl")
    plan = {
        "model": MODEL,
        "prompt": SYSTEM,
        "items": items,
        "batch_size": 5,
        "temperature": 0,
        "seed": 4016,
        "data_origin": "synthetic",
        "rubric_source_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
        "protocol": (
            "Per-item array variants bound claim indices/counts; unchanged calibration rubric"
        ),
    }
    path = ROOT / "plan.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != plan:
        raise ValueError("Frozen judge plan differs")
    path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    raw = ROOT / "model-labels.jsonl"
    done = (
        {json.loads(x)["id"] for x in raw.read_text(encoding="utf-8").splitlines()}
        if raw.exists()
        else set()
    )
    pending = [r for r in items if r["id"] not in done]
    key = dotenv_values(".env")["OPENROUTER_API_KEY"]
    async with httpx.AsyncClient(timeout=180) as client:
        for start in range(0, len(pending), 5):
            group = pending[start : start + 5]
            before = time.perf_counter()
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": "Bearer " + key},
                json={
                    "model": MODEL,
                    "temperature": 0,
                    "seed": 4016,
                    "max_tokens": 6000,
                    "reasoning": {"enabled": False},
                    "messages": [
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": json.dumps({"items": group})},
                    ],
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "record_judgements",
                                "description": "Label exactly supplied claims.",
                                "parameters": keyed_schema(group),
                            },
                        }
                    ],
                    "tool_choice": {"type": "function", "function": {"name": "record_judgements"}},
                },
            )
            if response.status_code != 200:
                raise RuntimeError(f"Free judge HTTP {response.status_code}; saved work retained")
            data = response.json()
            choice = data["choices"][0]
            with (ROOT / "calls.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "ids": [r["id"] for r in group],
                            "model": data.get("model"),
                            "usage": data.get("usage"),
                            "response_id": data.get("id"),
                            "finish_reason": choice.get("finish_reason"),
                            "elapsed_seconds": time.perf_counter() - before,
                        }
                    )
                    + "\n"
                )
            calls = choice["message"].get("tool_calls", [])
            if choice["finish_reason"] != "tool_calls" or len(calls) != 1:
                raise ValueError("Incomplete judge output; no labels accepted")
            arguments = calls[0]["function"]["arguments"]
            try:
                parsed = Batch.model_validate_json(arguments)
                validate_batch(group, parsed)
            except (ValueError, TypeError, KeyError):
                (ROOT / "invalid-response.txt").write_text(arguments, encoding="utf-8")
                raise
            with raw.open("a", encoding="utf-8") as handle:
                for item in parsed.items:
                    handle.write(item.model_dump_json() + "\n")
            print(f"Judge: {len(done) + start + len(group)}/{len(items)} recorded", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
