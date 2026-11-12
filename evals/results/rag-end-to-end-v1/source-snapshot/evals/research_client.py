"""Metered native function calls for real ReAct/supervisor research, never user sends."""

import asyncio
import json
import re
import time
from pathlib import Path
from uuid import uuid4

import httpx
from langchain_openai import ChatOpenAI

from agent.model_client import BudgetExceeded, ModelUnavailable
from agent.providers.groq import OPEN_MODELS, GroqGate


class ResearchBudget:
    """One reservation fence shared by native calls and optional verifier calls."""

    def __init__(self, limit=20000):
        self.limit, self.used, self.reserved = limit, 0, 0
        self.lock = asyncio.Lock()

    async def reserve(self, amount):
        async with self.lock:
            if self.used + self.reserved + amount > self.limit:
                raise BudgetExceeded("Research run token budget reached")
            self.reserved += amount

    async def settle(self, amount, actual):
        async with self.lock:
            self.reserved -= amount
            self.used += actual


class RequiredToolsChat(ChatOpenAI):
    def bind_tools(self, tools, *, tool_choice=None, parallel_tool_calls=None, **kwargs):
        return super().bind_tools(
            tools,
            tool_choice=tool_choice or "required",
            parallel_tool_calls=False if parallel_tool_calls is None else parallel_tool_calls,
            **kwargs,
        )


def normalized_failed_call(body, error):
    """Recover only a declared tool's transport name, never arguments or a decision."""
    if error.get("code") != "tool_use_failed":
        return None
    try:
        raw = json.loads(error.get("failed_generation", ""))
    except (TypeError, ValueError):
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("arguments"), dict):
        return None
    name = raw.get("name", "")
    if not isinstance(name, str):
        return None
    wrapped = re.fullmatch(
        r"(?:to=)?functions\.([A-Za-z_][A-Za-z_0-9]*)(?:<\|channel\|>(?:analysis|commentary))?",
        name,
    )
    canonical = wrapped.group(1) if wrapped else name
    declared = {t.get("function", {}).get("name") for t in body.get("tools", [])}
    if canonical not in declared:
        return None
    return {
        "id": "call_host_" + uuid4().hex,
        "type": "function",
        "function": {
            "name": canonical,
            "arguments": json.dumps(raw["arguments"]),
        },
    }


class ResearchTransport(httpx.AsyncBaseTransport):
    def __init__(self, settings, records, *, budget=None):
        self.records, self.budget = records, budget or ResearchBudget()
        self.gate = GroqGate(
            settings.groq_api_key.get_secret_value(),
            settings.redis_url,
            daily_tokens=settings.groq_daily_token_cap,
        )
        self.upstream = httpx.AsyncHTTPTransport()
        self.output_gate = GroqGate(
            settings.groq_api_key.get_secret_value(),
            settings.redis_url,
            tokens_per_minute=950,
            daily_tokens=settings.groq_daily_token_cap,
        )

    async def aclose(self):
        await self.upstream.aclose()

    async def handle_async_request(self, request):
        body = json.loads(request.content)
        maximum = body.get("max_completion_tokens", body.get("max_tokens", 1200))
        reservation = len(json.dumps(body)) // 3 + maximum
        await self.budget.reserve(reservation)
        before = len(self.records)
        try:
            return await self._send(request, body, maximum, reservation)
        finally:
            recorded = self.records[before:]
            charge = (
                sum(
                    r.get("reserved_tokens", 0)
                    if r.get("usage_known") is False
                    else r.get("input_tokens", 0) + r.get("output_tokens", 0)
                    for r in recorded
                )
                if recorded
                else reservation
            )
            await self.budget.settle(reservation, charge)

    async def _send(self, request, body, maximum, reservation):
        if request.url.host != "api.groq.com":
            raise ValueError("Research transport only supports the fixed Groq endpoint")
        if body["model"] not in OPEN_MODELS:
            raise ValueError("Unsupported open-weight research model")
        daily = await self.gate.reserve(body["model"], reservation)
        output_ticket = (
            await self.output_gate.reserve(body["model"] + ":output", maximum)
            if body["model"].startswith("qwen/")
            else None
        )
        start = time.perf_counter()
        response = await self.upstream.handle_async_request(request)
        await response.aread()
        if response.status_code != 200:
            provider_error = {}
            # Private pilot diagnostics contain only fictional research messages.
            # Never record authorization headers, credentials or entire requests.
            try:
                provider_error = response.json().get("error", {})
                diagnostic = {
                    "model": body["model"],
                    "status": response.status_code,
                    "type": provider_error.get("type"),
                    "code": provider_error.get("code"),
                    "message": re.sub(
                        r"\borg_[a-zA-Z0-9_]+", "[ORG]", str(provider_error.get("message", ""))
                    )[:1000],
                    "failed_generation": provider_error.get("failed_generation"),
                }
                with Path("work/research-provider-errors.jsonl").open("a", encoding="utf-8") as log:
                    log.write(json.dumps(diagnostic, ensure_ascii=True) + "\n")
            except (ValueError, OSError):
                pass
            self.records.append(
                {
                    "model": body["model"],
                    "status": response.status_code,
                    "usage_known": False,
                    "reserved_tokens": reservation,
                    "elapsed_seconds": time.perf_counter() - start,
                }
            )
            recovered = normalized_failed_call(body, provider_error)
            if recovered:
                # The tool's normal schema validation still rejects missing/invalid
                # arguments. Original HTTP failure and unknown usage remain recorded.
                self.records[-1].update(
                    host_normalized_tool_name=True,
                    tool_calls=[recovered["function"]["name"]],
                )
                return httpx.Response(
                    200,
                    request=request,
                    json={
                        "id": "host-normalized-" + uuid4().hex,
                        "object": "chat.completion",
                        "created": int(time.time()),
                        "model": body["model"],
                        "choices": [
                            {
                                "index": 0,
                                "finish_reason": "tool_calls",
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": [recovered],
                                },
                            }
                        ],
                    },
                )
            if response.status_code == 429:
                raise ModelUnavailable("Provider rate limit; research case remains pending")
            raise ModelUnavailable("Provider rejected the research call")
        data = response.json()
        usage = data.get("usage", {})
        actual = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
        await self.gate.settle(daily, reservation, actual)
        if output_ticket:
            await self.output_gate.settle(output_ticket, maximum, usage.get("completion_tokens", 0))
        message = data.get("choices", [{}])[0].get("message", {})
        self.records.append(
            {
                "model": body["model"],
                "status": 200,
                "usage_known": True,
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "elapsed_seconds": time.perf_counter() - start,
                "tool_calls": [
                    t.get("function", {}).get("name") for t in message.get("tool_calls", [])
                ],
                "finish_reason": data.get("choices", [{}])[0].get("finish_reason"),
            }
        )
        return response


def native_model(settings, model, records):
    budget = ResearchBudget()
    if model.startswith("gemini-"):
        from agent.providers.gemini import GeminiChatTransport, GeminiGate

        key = settings.google_api_key.get_secret_value()
        client = httpx.AsyncClient(
            transport=GeminiChatTransport(
                key,
                GeminiGate(key, settings.redis_url),
                records=records,
                budget=budget,
            ),
            timeout=180,
        )
        chat = RequiredToolsChat(
            model=model,
            api_key=key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            temperature=0,
            max_tokens=2000,
            reasoning_effort="minimal",
            max_retries=0,
            http_async_client=client,
            use_responses_api=False,
        )
        return chat, client, budget
    client = httpx.AsyncClient(
        transport=ResearchTransport(settings, records, budget=budget),
        timeout=180,
    )
    chat = RequiredToolsChat(
        model=model,
        api_key=settings.groq_api_key.get_secret_value(),
        base_url="https://api.groq.com/openai/v1",
        temperature=0,
        max_tokens=768 if model.startswith("qwen/") else 1200,
        reasoning_effort="none" if model.startswith("qwen/") else "low",
        max_retries=0,
        http_async_client=client,
        use_responses_api=False,
    )
    return chat, client, budget
