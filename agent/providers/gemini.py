"""Optional closed-model Gemini profile, fixed endpoint and preserved tool signatures."""

import asyncio
import hashlib
import json
import time
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from redis.asyncio import Redis

from agent.costs import priced_usage
from agent.model_client import ModelUnavailable, OllamaModels

GEMINI_MODELS = {"gemini-3.1-flash-lite", "gemini-3.5-flash-lite"}
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"


class GeminiGate:
    def __init__(self, key, redis_url, *, daily_limit=480):
        self.identity = hashlib.sha256(key.encode()).hexdigest()[:20]
        self.redis_url, self.daily_limit = redis_url, daily_limit

    def keys(self, model):
        day = datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y%m%d")
        root = "gigbid:gemini:" + self.identity + ":" + model
        return root + ":day:" + day, root + ":minute"

    async def available(self, model, headroom=20):
        daily, _ = self.keys(model)
        async with Redis.from_url(self.redis_url, socket_timeout=3) as redis:
            used = int(await redis.get(daily) or 0)
        return self.daily_limit - used >= headroom

    async def reserve(self, model):
        if model not in GEMINI_MODELS:
            raise ValueError("Select an explicitly configured Gemini Flash-Lite model")
        daily, minute = self.keys(model)
        script = """
        if tonumber(redis.call('GET',KEYS[1]) or '0')>=tonumber(ARGV[1]) then return -1 end
        local t=redis.call('TIME');local now=tonumber(t[1])+tonumber(t[2])/1000000
        redis.call('ZREMRANGEBYSCORE',KEYS[2],'-inf',now-60)
        if redis.call('ZCARD',KEYS[2])>=10 then
          local oldest=redis.call('ZRANGE',KEYS[2],0,0,'WITHSCORES')
          return math.max(1,math.ceil(60+tonumber(oldest[2])-now))
        end
        redis.call('INCR',KEYS[1]);redis.call('EXPIRE',KEYS[1],172800)
        redis.call('ZADD',KEYS[2],now,ARGV[2]);redis.call('EXPIRE',KEYS[2],120)
        return 0
        """
        async with Redis.from_url(self.redis_url, socket_timeout=3) as redis:
            for _ in range(10):
                delay = await redis.eval(script, 2, daily, minute, self.daily_limit, uuid4().hex)
                if delay == -1:
                    raise ModelUnavailable("Gemini daily allowance reached; retry after reset")
                if delay == 0:
                    return
                await asyncio.sleep(min(delay, 30))
        raise ModelUnavailable("Gemini request allowance is busy; retry later")


class GeminiChatTransport(httpx.AsyncBaseTransport):
    def __init__(
        self, key, gate, *, records=None, budget=None, upstream=None, timeout=180, retry_record=None
    ):
        self.key, self.gate, self.records, self.budget = key, gate, records, budget
        self.upstream, self.timeout, self.signatures = upstream, timeout, {}
        self.retry_record = retry_record

    async def handle_async_request(self, request):
        if request.url.host != "generativelanguage.googleapis.com":
            raise ValueError("Gemini transport only supports Google's fixed API endpoint")
        body = json.loads(request.content)
        if body.get("model") not in GEMINI_MODELS:
            raise ValueError("Unsupported Gemini model")
        body["max_tokens"] = body.pop("max_completion_tokens", body.get("max_tokens", 2000))
        body["reasoning_effort"] = "minimal"
        # LangChain may normalize away this provider extension. Preserve the exact
        # signature returned for this run's call ID; never invent or decode one.
        for message in body.get("messages", []):
            if message.get("role") == "assistant":
                for call in message.get("tool_calls", []):
                    if call.get("id") in self.signatures:
                        call["extra_content"] = self.signatures[call["id"]]
        reservation = len(json.dumps(body)) // 3 + body["max_tokens"]
        charged, recorded = reservation, False
        reserved_total, failed_charge = reservation, 0
        if self.budget:
            await self.budget.reserve(reservation)
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.upstream) as client:
                for attempt in range(3):
                    await self.gate.reserve(body["model"])
                    response = await client.post(
                        ENDPOINT,
                        headers={"Authorization": "Bearer " + self.key},
                        json=body,
                    )
                    if response.status_code not in {500, 502, 503, 504} or attempt == 2:
                        break
                    if self.records is not None:
                        self.records.append(
                            {
                                "provider": "gemini",
                                "model": body["model"],
                                "status": response.status_code,
                                "usage_known": False,
                                "reserved_tokens": reservation,
                                "transient_retry": attempt + 1,
                            }
                        )
                    if self.budget:
                        # Unknown failed-call usage remains conservatively charged.
                        await self.budget.reserve(reservation)
                        reserved_total += reservation
                    if self.retry_record:
                        await self.retry_record(
                            {
                                "provider": "gemini",
                                "model": body["model"],
                                "role": "transport_retry",
                                "usage_known": False,
                                "input_tokens": None,
                                "output_tokens": None,
                                "reserved_tokens": reservation,
                                "http_status": response.status_code,
                            }
                        )
                    failed_charge += reservation
                    await asyncio.sleep(2 ** (attempt + 1))
            if response.status_code != 200:
                if self.records is not None:
                    self.records.append(
                        {
                            "provider": "gemini",
                            "model": body["model"],
                            "status": response.status_code,
                            "usage_known": False,
                            "reserved_tokens": reservation,
                        }
                    )
                    recorded = True
                if response.status_code == 429:
                    raise ModelUnavailable("Gemini provider rate limit; retry later")
                if response.status_code in {500, 502, 503, 504}:
                    raise ModelUnavailable("Gemini provider temporarily unavailable")
                raise ModelUnavailable("Gemini API rejected the schema or request")
            data = response.json()
            usage = data["usage"]
            charged = usage["prompt_tokens"] + usage["completion_tokens"]
            for choice in data.get("choices", []):
                for call in choice.get("message", {}).get("tool_calls", []):
                    if call.get("id") and call.get("extra_content"):
                        self.signatures[call["id"]] = call["extra_content"]
            if self.records is not None:
                self.records.append(
                    {
                        "provider": "gemini",
                        "model": body["model"],
                        "status": 200,
                        "usage_known": True,
                        "input_tokens": usage["prompt_tokens"],
                        "output_tokens": usage["completion_tokens"],
                        "elapsed_seconds": time.perf_counter() - started,
                        "tool_calls": [
                            c["function"]["name"]
                            for c in data["choices"][0]["message"].get("tool_calls", [])
                        ],
                        "finish_reason": data["choices"][0].get("finish_reason"),
                        "usd": None,
                    }
                )
                recorded = True
            return httpx.Response(200, request=request, json=data)
        finally:
            if self.records is not None and not recorded:
                self.records.append(
                    {
                        "provider": "gemini",
                        "model": body["model"],
                        "status": None,
                        "usage_known": False,
                        "reserved_tokens": charged,
                    }
                )
            if self.budget:
                await self.budget.settle(reserved_total, charged + failed_charge)


class GeminiOllamaTransport(httpx.AsyncBaseTransport):
    def __init__(self, chat):
        self.chat = chat

    async def handle_async_request(self, request):
        old = json.loads(request.content)
        body = {
            "model": old["model"],
            "messages": old["messages"],
            "temperature": 0,
            "max_tokens": old["options"]["num_predict"],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "gigbid_handoff",
                    "strict": False,
                    "schema": old["format"],
                },
            },
        }
        result = await self.chat.handle_async_request(httpx.Request("POST", ENDPOINT, json=body))
        data = result.json()
        choice, usage = data["choices"][0], data["usage"]
        content = choice["message"].get("content", "") if choice["finish_reason"] == "stop" else ""
        return httpx.Response(
            200,
            request=request,
            json={
                "message": {"content": content},
                "prompt_eval_count": usage["prompt_tokens"],
                "eval_count": usage["completion_tokens"],
                "eval_duration": 0,
            },
        )


class GeminiModels(OllamaModels):
    def __init__(
        self, base_url, config, *, api_key=None, gate=None, upstream=None, record=None, **kwargs
    ):
        from apps.api.settings import Settings

        settings = Settings()
        key = api_key or settings.google_api_key.get_secret_value()
        if not key:
            raise ModelUnavailable("Configure GOOGLE_API_KEY for the optional Gemini profile")
        gate = gate or GeminiGate(key, settings.redis_url)

        async def record_hosted(metrics):
            if record:
                await record(
                    priced_usage(
                        {
                            **metrics,
                            "provider": "gemini",
                            "usd": None,
                            "generation_seconds": None,
                            "cost_basis": "Gemini API; actual billing not verified",
                        }
                    )
                )

        chat = GeminiChatTransport(
            key, gate, upstream=upstream, timeout=config.timeout, retry_record=record_hosted
        )
        super().__init__(
            "http://gemini-translation",
            config,
            transport=GeminiOllamaTransport(chat),
            record=record_hosted,
            **kwargs,
        )
