"""Keep valid labels; retry only malformed items, never revise accepted assessments."""

import asyncio
import hashlib
import json
from collections import Counter, deque
from pathlib import Path

import httpx
from dotenv import dotenv_values

from evals.judge_indexed import keyed_schema
from evals.research_judge import MODEL, PROMPT, Batch, proposal_inputs, validate_batch

ROOT = Path("evals/results/judge-proposals-final")


async def main(items=None, *, output=ROOT):
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    original_cohort = items is None
    if original_cohort:
        items = proposal_inputs("evals/results/gemini-orchestration-v1/runs.jsonl")
    expected = {r["id"]: r for r in items}
    plan = {
        "model": MODEL,
        "prompt": PROMPT,
        "items": items,
        "temperature": 0,
        "seed": 4016,
        "data_origin": "synthetic",
        "rubric_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
        "protocol": (
            "Batch five; accept each exact validated item; retry malformed items"
            " individually at most twice. Accepted labels never replaced."
        ),
        "reuse": ["judge-proposals-v1/model-labels.jsonl", "judge-proposals-v3/model-labels.jsonl"]
        if original_cohort
        else [],
        "reuse_rule": (
            "First available validated observation in listed source order; no score-based selection"
        ),
    }
    path = root / "plan.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != plan:
        raise ValueError("Frozen final-judge plan differs")
    path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    raw = root / "model-labels.jsonl"
    accepted = (
        {json.loads(x)["id"]: json.loads(x) for x in raw.read_text(encoding="utf-8").splitlines()}
        if raw.exists()
        else {}
    )

    def accept(value):
        identity = value["id"]
        validate_batch([expected[identity]], Batch.model_validate({"items": [value]}))
        if identity not in accepted:
            with raw.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(value) + "\n")
            accepted[identity] = value

    for source in plan["reuse"]:
        for line in (Path("evals/results") / source).read_text(encoding="utf-8").splitlines():
            accept(json.loads(line))
    pending = [r for r in items if r["id"] not in accepted]
    queue = deque([pending[i : i + 5] for i in range(0, len(pending), 5)])
    attempts = Counter()
    key = dotenv_values(".env")["OPENROUTER_API_KEY"]
    async with httpx.AsyncClient(timeout=180) as client:
        while queue:
            group = [r for r in queue.popleft() if r["id"] not in accepted]
            if not group:
                continue
            for item in group:
                attempts[item["id"]] += 1
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": "Bearer " + key},
                json={
                    "model": MODEL,
                    "temperature": 0,
                    "seed": 4016,
                    "max_tokens": 5000,
                    "reasoning": {"enabled": False},
                    "messages": [
                        {"role": "system", "content": PROMPT},
                        {"role": "user", "content": json.dumps({"items": group})},
                    ],
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "record_judgements",
                                "description": (
                                    "Assess exactly the supplied claim indices "
                                    "without splitting them."
                                ),
                                "parameters": keyed_schema(group),
                            },
                        }
                    ],
                    "tool_choice": {"type": "function", "function": {"name": "record_judgements"}},
                },
            )
            if response.status_code != 200:
                raise RuntimeError(f"Free judge HTTP {response.status_code}; accepted labels saved")
            data = response.json()
            with (root / "calls.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "ids": [r["id"] for r in group],
                            "usage": data.get("usage"),
                            "model": data.get("model"),
                            "response_id": data.get("id"),
                        }
                    )
                    + "\n"
                )
            try:
                choice = data["choices"][0]
                calls = choice["message"].get("tool_calls", [])
                if choice["finish_reason"] != "tool_calls" or len(calls) != 1:
                    raise ValueError("Incomplete output")
                content = calls[0]["function"]["arguments"]
                values = Batch.model_validate_json(content).items
                returned = Counter(v.id for v in values)
                for value in values:
                    if returned[value.id] == 1 and value.id in {r["id"] for r in group}:
                        try:
                            accept(value.model_dump())
                        except ValueError:
                            pass
                with (root / "raw-responses.jsonl").open("a", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps({"ids": [r["id"] for r in group], "arguments": content}) + "\n"
                    )
            except (ValueError, KeyError, TypeError):
                pass
            invalid = [r for r in group if r["id"] not in accepted]
            if any(attempts[r["id"]] >= 3 for r in invalid):
                raise ValueError("Judge failed exact-index validation after bounded retries")
            for item in invalid:
                queue.append([item])
            print(
                f"Judge: {len(accepted)}/{len(items)} accepted; {len(invalid)} queued individually",
                flush=True,
            )
            await asyncio.sleep(3.2)
    validate_batch(items, Batch.model_validate({"items": list(accepted.values())}))


if __name__ == "__main__":
    asyncio.run(main())
