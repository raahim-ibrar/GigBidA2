"""Structured local inference. No prompts, credentials or raw portfolio text are logged."""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from agent.config import AgentConfig

T = TypeVar("T", bound=BaseModel)


class ModelUnavailable(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    pass


class OllamaModels:
    def __init__(
        self,
        base_url: str,
        config: AgentConfig,
        *,
        record=None,
        transport=None,
        tokens_used: int = 0,
    ):
        self.base_url, self.config = base_url.rstrip("/"), config
        self.record: Callable[[dict], Awaitable[None]] | None = record
        self.tokens = tokens_used
        self.transport = transport
        self._reserved = 0
        self._lock = asyncio.Lock()

    async def complete(self, role: str, payload: dict, schema: type[T]) -> T:
        body = json.dumps(payload, ensure_ascii=False)
        prompt = self.config.prompt(role)
        schema_json = schema.model_json_schema()
        if len(body) > 60000:
            raise BudgetExceeded(
                "Agent input exceeds the configured context; shorten the job or draft"
            )
        # Reserve for concurrent branches and fallback attempts, including the system
        # prompt, structured-output schema and output allowance. Actual usage replaces
        # the estimate on success. Unknown usage after a transport failure remains
        # charged conservatively, rather than allowing repeated free retries.
        reserve = (len(body) + len(prompt) + len(json.dumps(schema_json))) // 3
        reserve += self.config.output_tokens
        if reserve > self.config.context_size:
            raise BudgetExceeded("Agent input exceeds the model context; shorten the job or draft")
        candidates = [self.config.models[role]]
        if self.config.fallback and role not in {"writer", "critic", "verifier"}:
            candidates.append(self.config.fallback)
        for attempt, model in enumerate(candidates):
            async with self._lock:
                if (
                    self.tokens + self._reserved + reserve
                    > self.config.budgets.max_tokens_per_thread
                ):
                    raise BudgetExceeded("The run's token budget has been reached")
                self._reserved += reserve
            started = time.monotonic()
            charged = reserve
            try:
                async with httpx.AsyncClient(
                    timeout=self.config.timeout,
                    transport=self.transport,
                ) as client:
                    response = await client.post(
                        self.base_url + "/api/chat",
                        json={
                            "model": model,
                            "stream": False,
                            "think": False,
                            "format": schema_json,
                            "messages": [
                                {"role": "system", "content": prompt},
                                {"role": "user", "content": body},
                            ],
                            "options": {
                                "temperature": 0,
                                "num_ctx": self.config.context_size,
                                "num_predict": self.config.output_tokens,
                                "seed": 42,
                            },
                        },
                    )
                    response.raise_for_status()
                    result = response.json()
                counts = [result["prompt_eval_count"], result["eval_count"]]
                if any(type(count) is not int or count < 0 for count in counts):
                    raise ValueError("Invalid model usage")
                charged = sum(counts)
                metrics = {
                    "role": role,
                    "model": model,
                    "provider": "ollama",
                    "attempt": attempt + 1,
                    "input_tokens": result.get("prompt_eval_count", 0),
                    "output_tokens": result.get("eval_count", 0),
                    "elapsed_seconds": round(time.monotonic() - started, 4),
                    "generation_seconds": result.get("eval_duration", 0) / 1e9,
                    "usd": 0.0,
                    "cost_basis": "local inference; hardware and electricity excluded",
                }
                if self.record:
                    await self.record(metrics)
                if self.tokens + charged > self.config.budgets.max_tokens_per_thread:
                    raise BudgetExceeded("The run's token budget has been reached")
                return schema.model_validate_json(result["message"]["content"])
            except (httpx.HTTPError, ValidationError, ValueError, KeyError):
                if attempt + 1 == len(candidates):
                    raise ModelUnavailable(
                        f"{role} could not complete with its configured model. "
                        "Check Ollama/model availability."
                    ) from None
            finally:
                async with self._lock:
                    self.tokens += charged
                    self._reserved -= reserve
        raise ModelUnavailable("No model is configured")
