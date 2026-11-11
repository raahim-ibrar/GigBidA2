"""Groq transport reuses the same validated handoffs and durable token accounting.

Only inference is translated; tool permissions, evidence checks and approval remain
in the graph/host. No credentials or prompts are included in usage records.
"""

import asyncio
import hashlib
import json
import os
import time

import httpx
from redis.asyncio import Redis

from agent.model_client import BudgetExceeded, ModelUnavailable, OllamaModels

OPEN_MODELS = {"openai/gpt-oss-120b", "openai/gpt-oss-20b"}


class GroqGate:
    def __init__(self, key, redis_url, *, tokens_per_minute=7500, daily_tokens=150000):
        self.identity = hashlib.sha256(key.encode()).hexdigest()[:20]
        self.redis_url, self.capacity, self.daily_tokens = (
            redis_url,
            tokens_per_minute,
            daily_tokens,
        )

    async def reserve(self, model, amount):
        if amount > self.capacity:
            raise BudgetExceeded("Groq prompt/output reservation exceeds configured TPM allowance")
        root = "gigbid:groq:" + self.identity + ":" + model
        day = str(int(time.time() // 86400))
        daily = root + ":daily:" + day
        script = """
        local used=tonumber(redis.call('GET',KEYS[2]) or '0')
        if used+tonumber(ARGV[2])>tonumber(ARGV[3]) then return -1 end
        local t=redis.call('TIME'); local now=tonumber(t[1])+tonumber(t[2])/1000000
        local old=redis.call('HMGET',KEYS[1],'tokens','time')
        local cap=tonumber(ARGV[1]); local cost=tonumber(ARGV[2])
        local tokens=math.min(cap,tonumber(old[1] or cap)+(now-tonumber(old[2] or now))*cap/60)
        if tokens<cost then return math.ceil((cost-tokens)*60/cap) end
        redis.call('HSET',KEYS[1],'tokens',tokens-cost,'time',now)
        redis.call('EXPIRE',KEYS[1],120)
        redis.call('INCRBY',KEYS[2],cost);redis.call('EXPIRE',KEYS[2],172800)
        return 0
        """
        async with Redis.from_url(self.redis_url, socket_timeout=3) as redis:
            for _ in range(6):
                wait = await redis.eval(
                    script, 2, root + ":bucket", daily, self.capacity, amount, self.daily_tokens
                )
                if wait == -1:
                    raise BudgetExceeded("Groq daily study token cap reached; resume after reset")
                if wait == 0:
                    return daily
                await asyncio.sleep(min(wait, 30))
        raise ModelUnavailable("Groq token allowance is busy; retry the saved step later")

    async def settle(self, daily, reserved, actual):
        unused = max(0, reserved - actual)
        if unused:
            async with Redis.from_url(self.redis_url, socket_timeout=3) as redis:
                await redis.decrby(daily, unused)


class GroqTransport(httpx.AsyncBaseTransport):
    def __init__(self, api_key, gate, *, upstream=None, timeout=90):
        self.key, self.gate, self.upstream, self.timeout = api_key, gate, upstream, timeout

    async def handle_async_request(self, request):
        original = json.loads(request.content)
        model = original["model"]
        if model not in OPEN_MODELS:
            raise ValueError("Select an explicitly supported open-weight Groq model")
        options = original["options"]
        maximum = options["num_predict"]
        amount = (len(json.dumps(original["messages"])) + len(json.dumps(original["format"]))) // 3
        amount += maximum
        daily = await self.gate.reserve(model, amount)
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.upstream) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": "Bearer " + self.key,
                },
                json={
                    "model": model,
                    "messages": original["messages"],
                    "stream": False,
                    "temperature": options["temperature"],
                    "max_completion_tokens": maximum,
                    "reasoning_effort": "low",
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "gigbid_handoff",
                            "strict": False,
                            "schema": original["format"],
                        },
                    },
                },
            )
        if response.status_code != 200:
            # Do not expose raw provider bodies; errors may echo prompt/account data.
            return httpx.Response(
                response.status_code,
                request=request,
                json={"error": "Groq unavailable or quota/schema rejected"},
            )
        body = response.json()
        usage = body.get("usage", {})
        actual = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
        await self.gate.settle(daily, amount, actual)
        choice = body["choices"][0]
        if choice.get("finish_reason") != "stop" or not choice["message"].get("content"):
            return httpx.Response(503, request=request, json={"error": "Incomplete Groq handoff"})
        return httpx.Response(
            200,
            request=request,
            json={
                "message": {"content": choice["message"]["content"]},
                "prompt_eval_count": usage.get("prompt_tokens", 0),
                "eval_count": usage.get("completion_tokens", 0),
                "eval_duration": 0,
            },
        )


class GroqModels(OllamaModels):
    def __init__(
        self,
        base_url,
        config,
        *,
        api_key=None,
        redis_url=None,
        gate=None,
        upstream=None,
        record=None,
        **kwargs,
    ):
        from apps.api.settings import Settings

        settings = Settings()
        api_key = api_key or os.getenv("GROQ_API_KEY") or settings.groq_api_key.get_secret_value()
        if not api_key:
            raise ModelUnavailable("Configure GROQ_API_KEY for the hosted open-weight profile")
        gate = gate or GroqGate(api_key, redis_url or settings.redis_url)

        async def record_hosted(metrics):
            if record:
                await record(
                    {
                        **metrics,
                        "provider": "groq",
                        "usd": None,
                        "generation_seconds": None,
                        "cost_basis": "Actual billing not verified; inspect Groq usage",
                    }
                )

        super().__init__(
            "http://groq-translation",
            config,
            transport=GroqTransport(api_key, gate, upstream=upstream, timeout=config.timeout),
            record=record_hosted,
            **kwargs,
        )
