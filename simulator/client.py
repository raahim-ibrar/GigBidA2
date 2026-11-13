"""Durable outbox resolver for the optional open-model simulated client."""

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Literal

import httpx
import yaml
from pydantic import BaseModel, ConfigDict


class ClientDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["ignore", "reply", "interview", "hire"]


async def decide(claim):
    root = Path(__file__).resolve().parent
    config = yaml.safe_load((root / "client_config.yaml").read_text(encoding="utf-8"))
    job = claim["job"]
    payload = {
        "job": {
            key: job[key]
            for key in (
                "title",
                "description",
                "required_skills",
                "budget_min",
                "budget_max",
                "screening_questions",
            )
        },
        "proposal": claim["request"],
        "private_preferences": {
            "must_have_skills": job["required_skills"],
            "budget_ceiling": job["budget_max"],
            "dislike_generic_openings": True,
        },
    }
    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=config["timeout_seconds"]) as client:
        response = await client.post(
            os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434") + "/api/chat",
            json={
                "model": config["model"],
                "stream": False,
                "think": False,
                "format": ClientDecision.model_json_schema(),
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            root.parent / "agent/prompts/experiments/simulator_client.md"
                        ).read_text(encoding="utf-8"),
                    },
                    {"role": "user", "content": json.dumps(payload)},
                ],
                "options": {
                    "temperature": config["temperature"],
                    "seed": config["seed"],
                    "num_ctx": config["context_size"],
                    "num_predict": config["output_tokens"],
                },
            },
        )
        response.raise_for_status()
        body = response.json()
    decision = ClientDecision.model_validate_json(body["message"]["content"])
    return decision.decision, {
        "model": config["model"],
        "input_tokens": body.get("prompt_eval_count"),
        "output_tokens": body.get("eval_count"),
        "elapsed_seconds": time.perf_counter() - started,
        "inference_api_usd": 0,
    }


async def tick(store, *, resolver=decide):
    claim = await asyncio.to_thread(store.claim_client, time.time())
    if not claim:
        return False
    try:
        decision, metrics = await resolver(claim)
        await asyncio.to_thread(store.resolve_client, claim, decision, metrics)
    except Exception:
        # Keep the debit/submission receipt. Never manufacture a negative outcome on an outage.
        await asyncio.to_thread(store.client_failed, claim, time.time())
    return True


async def resolve_forever(store):
    while True:
        await tick(store)
        await asyncio.sleep(2)
