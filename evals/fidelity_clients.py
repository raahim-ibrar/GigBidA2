"""Bounded LLM-client replay of frozen submissions; no agent reruns or real sends."""

import asyncio
import hashlib
import json
import subprocess
import time
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import httpx
from dotenv import dotenv_values

from agent.marketplace_port import ProposalWrite
from simulator.store import SimStore

ROOT = Path("evals/results/evaluation-fidelity-v1")
MODEL = "nvidia/nemotron-3.5-lightning:free"
MAX_CALLS = 12


def verify_synthetic_sources(rows, catalogues, sources):
    """Fail closed: export only unchanged, already-public synthetic research records."""
    for paths in sources.values():
        for path in paths:
            public = subprocess.check_output(["git", "show", "HEAD:" + path.as_posix()])
            expected = list(map(json.loads, public.decode("utf-8").splitlines()))
            actual = list(map(json.loads, path.read_text(encoding="utf-8").splitlines()))
            if actual != expected:
                raise ValueError("Source differs from its reviewed public Git revision")
    if not all(
        j.get("synthetic") is True and j["id"].startswith("student-4016-")
        for jobs in catalogues.values()
        for j in jobs
    ):
        raise ValueError("Only the registered synthetic catalogue may be replayed")
    evidence_count = 0
    for row in rows:
        for item in row.get("evidence") or row["snapshot"].get("evidence", []):
            evidence_count += 1
            if not (
                item.get("persona") in {"ai_ml", "full_stack", "data_analyst"}
                and item.get("project", "").startswith("Demo ")
                and any(word in item["text"].lower() for word in ["synthetic", "fictional"])
            ):
                raise ValueError("Evidence provenance is not exclusively synthetic")
    return {
        "sources_match_public_git": True,
        "synthetic_jobs_only": True,
        "evidence_records_checked": evidence_count,
        "payload": "Job and frozen proposal only; no evidence bodies, CV or credentials",
        "destination": "https://openrouter.ai/api/v1/chat/completions",
    }


def frozen_rows():
    sources = {
        "architecture": [Path("evals/results/gemini-orchestration-v1/runs.jsonl")],
        "rag": [
            Path(f"evals/results/rag-end-to-end-v1/{v}/hosted_open-routed.jsonl")
            for v in ["v0", "v3"]
        ],
    }
    rows, jobs = [], {}
    for group, paths in sources.items():
        plan = (
            Path("evals/results/gemini-orchestration-v1/plan.json")
            if group == "architecture"
            else Path("evals/results/rag-end-to-end-v1/paired-plan.json")
        )
        data = json.loads(plan.read_text(encoding="utf-8"))
        jobs[group] = data["jobs"] if group == "architecture" else data["cohort"]
        for path in paths:
            for row in map(json.loads, path.read_text(encoding="utf-8").splitlines()):
                condition = row["condition"] if group == "architecture" else path.parent.name
                rows.append({**row, "group": group, "condition": condition})
    assert len(rows) == 168
    return rows, jobs, sources


def request_for(row):
    draft = row.get("candidate") or row["snapshot"]["draft"]
    price = draft.get("price") or (row["snapshot"].get("price") or {}).get("amount")
    return ProposalWrite(
        job_id=row["id"],
        text=draft["text"],
        bid_amount=price,
        screening_answers=draft.get("screening_answers", {}),
        idempotency_key="llm-replay:" + row["opaque_id"],
        dry_run=False,
    )


def client_payload(row, job):
    request = request_for(row)
    return {
        "id": row["opaque_id"],
        "job": {
            k: job[k]
            for k in [
                "title",
                "description",
                "required_skills",
                "budget_min",
                "budget_max",
                "screening_questions",
            ]
        },
        "proposal": request.model_dump(exclude={"job_id", "idempotency_key", "dry_run"}),
        "private_preferences": {
            "must_have_skills": job["required_skills"],
            "budget_ceiling": job["budget_max"],
            "dislike_generic_openings": True,
        },
    }


def decision_schema(ids):
    value = {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": ["ignore", "reply", "interview", "hire"]},
            "reason": {"type": "string", "maxLength": 400},
        },
        "required": ["decision", "reason"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "decisions": {
                "type": "object",
                "properties": {i: value for i in ids},
                "required": ids,
                "additionalProperties": False,
            }
        },
        "required": ["decisions"],
        "additionalProperties": False,
    }


def read_lines(path):
    return (
        list(map(json.loads, path.read_text(encoding="utf-8").splitlines()))
        if path.exists()
        else []
    )


def append(path, value):
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(value) + "\n")


async def run():
    ROOT.mkdir(parents=True, exist_ok=True)
    rows, catalogues, sources = frozen_rows()
    review = verify_synthetic_sources(rows, catalogues, sources)
    (ROOT / "export-provenance.json").write_text(json.dumps(review, indent=2), encoding="utf-8")
    for row in rows:
        row["opaque_id"] = hashlib.sha256(
            f"{row['group']}:{row['condition']}:{row['id']}".encode()
        ).hexdigest()[:20]
    submitted = [r for r in rows if r["outcome"]["submitted"]]
    assert len(submitted) == 92
    lookup = {g: {j["id"]: j for j in jobs} for g, jobs in catalogues.items()}
    items = [client_payload(r, lookup[r["group"]][r["id"]]) for r in submitted]
    prompt = Path("agent/prompts/experiments/client_outcomes.md").read_text(encoding="utf-8")
    plan = {
        "kind": "LLM-client replay of already-frozen research submissions",
        "model": MODEL,
        "temperature": 0,
        "seed": 4016,
        "batch_size": 10,
        "max_calls": MAX_CALLS,
        "max_output_tokens": 2000,
        "prompt": prompt,
        "source_sha256": {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for paths in sources.values()
            for p in paths
        },
        "items": items,
        "data_origin": "synthetic",
        "gpu_inference": False,
        "limits": "Generator observations are reused unchanged; only client decisions "
        "are new. Fixed budget/eligibility guards remain before effective replies/hires. "
        "Batched one-pass decisions can have cross-item context effects. No rule fallback, "
        "no paid fallback, no real marketplace access. Missing model decisions stay pending.",
    }
    path = ROOT / "client-plan.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != plan:
        raise ValueError("Frozen client plan changed")
    path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    accepted = {r["id"]: r for r in read_lines(ROOT / "client-decisions.jsonl")}
    attempts = len(read_lines(ROOT / "client-attempts.jsonl"))
    key = dotenv_values(".env").get("OPENROUTER_API_KEY")
    if len(accepted) < len(items) and not key:
        raise ValueError("Configured free OpenRouter key is required")
    async with httpx.AsyncClient(timeout=90) as client:
        while len(accepted) < len(items):
            if attempts >= MAX_CALLS:
                raise RuntimeError("Fixed client-request cap reached; remaining outcomes pending")
            group = [r for r in items if r["id"] not in accepted][:10]
            ids = [r["id"] for r in group]
            attempts += 1
            append(ROOT / "client-attempts.jsonl", {"attempt": attempts, "ids": ids})
            started = time.perf_counter()
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": "Bearer " + key},
                json={
                    "model": MODEL,
                    "temperature": 0,
                    "seed": 4016,
                    "max_tokens": 2000,
                    "reasoning": {"enabled": False},
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": json.dumps({"clients": group})},
                    ],
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "record_client_decisions",
                                "description": "Record each client decision.",
                                "parameters": decision_schema(ids),
                            },
                        }
                    ],
                    "tool_choice": {
                        "type": "function",
                        "function": {"name": "record_client_decisions"},
                    },
                },
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"Free client model HTTP {response.status_code}; outcomes pending"
                )
            body = response.json()
            append(
                ROOT / "client-calls.jsonl",
                {
                    "attempt": attempts,
                    "ids": ids,
                    "model": body.get("model"),
                    "usage": body.get("usage"),
                    "response_id": body.get("id"),
                    "seconds": time.perf_counter() - started,
                },
            )
            append(ROOT / "client-raw-responses.jsonl", body)
            try:
                choice = body["choices"][0]
                calls = choice["message"].get("tool_calls", [])
                if choice["finish_reason"] != "tool_calls" or len(calls) != 1:
                    raise ValueError("Incomplete client response")
                if calls[0]["function"]["name"] != "record_client_decisions":
                    raise ValueError("Unexpected client function")
                decisions = json.loads(calls[0]["function"]["arguments"])["decisions"]
                for identity, decision in decisions.items():
                    if identity not in ids or identity in accepted:
                        continue
                    if decision.get("decision") not in {"ignore", "reply", "interview", "hire"}:
                        continue
                    if not isinstance(decision.get("reason"), str):
                        continue
                    record = {"id": identity, **decision, "attempt": attempts}
                    append(ROOT / "client-decisions.jsonl", record)
                    accepted[identity] = record
            except (ValueError, KeyError, TypeError):
                pass
            print(f"LLM clients: {len(accepted)}/92 decisions, {attempts}/12 requests", flush=True)
            await asyncio.sleep(3.2)
    # Resolve through the existing simulator's actual LLM-mode outbox and guards.
    stores = {
        g: SimStore(ROOT / (g + ".sqlite"), jobs, client_mode="llm")
        for g, jobs in catalogues.items()
    }
    outcomes = []
    for row in rows:
        outcome = {
            "id": row["id"],
            "group": row["group"],
            "condition": row["condition"],
            "persona": row["persona"],
            "strategy": row.get("strategy"),
            "submitted": row["outcome"]["submitted"],
            "replied": False,
            "hired": False,
            "client_model_called": False,
            "followup_complete": True,
        }
        if row["outcome"]["submitted"]:
            tenant = str(uuid5(NAMESPACE_URL, "llm-client-replay:" + row["opaque_id"]))
            store = stores[row["group"]]
            receipt = store.write(tenant, "submit_proposal", request_for(row).model_dump())
            claim = store.claim_client(time.time())
            if claim:
                assert claim["proposal_id"] == receipt["id"]
                store.resolve_client(
                    claim,
                    accepted[row["opaque_id"]]["decision"],
                    {"model": MODEL, "batch_attempt": accepted[row["opaque_id"]]["attempt"]},
                )
            stages = [e["stage"] for e in store.events(tenant)]
            outcome.update(
                replied="replied" in stages,
                hired="hired" in stages,
                client_model_called=True,
                raw_decision=accepted[row["opaque_id"]],
            )
        outcomes.append(outcome)
    (ROOT / "llm-outcomes.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in outcomes), encoding="utf-8"
    )
    print("LLM-client outcomes complete: 168 assigned cases, 92 frozen submissions", flush=True)


if __name__ == "__main__":
    asyncio.run(run())
