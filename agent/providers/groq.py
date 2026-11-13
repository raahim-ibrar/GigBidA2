"""Groq transport reuses the same validated handoffs and durable token accounting.

Only inference is translated; tool permissions, evidence checks and approval remain
in the graph/host. No credentials or prompts are included in usage records.
"""

import asyncio
import hashlib
import json
import os
import time
from uuid import uuid4

import httpx
from redis.asyncio import Redis

from agent.costs import priced_usage
from agent.model_client import BudgetExceeded, ModelUnavailable, OllamaModels

OPEN_MODELS = {"openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"}


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
        member = uuid4().hex
        script = """
        local used=tonumber(redis.call('GET',KEYS[2]) or '0')
        if used+tonumber(ARGV[2])>tonumber(ARGV[3]) then return -1 end
        local t=redis.call('TIME'); local now=tonumber(t[1])+tonumber(t[2])/1000000
        local expired=redis.call('ZRANGEBYSCORE',KEYS[1],'-inf',now-60)
        for _,id in ipairs(expired) do redis.call('HDEL',KEYS[3],id) end
        redis.call('ZREMRANGEBYSCORE',KEYS[1],'-inf',now-60)
        local total=0
        for _,v in ipairs(redis.call('HVALS',KEYS[3])) do total=total+tonumber(v) end
        local cap=tonumber(ARGV[1]); local cost=tonumber(ARGV[2])
        if total+cost>cap or redis.call('ZCARD',KEYS[1])>=25 then
          local oldest=redis.call('ZRANGE',KEYS[1],0,0,'WITHSCORES')
          return math.max(1,math.ceil(60+tonumber(oldest[2])-now))
        end
        redis.call('ZADD',KEYS[1],now,ARGV[4])
        redis.call('HSET',KEYS[3],ARGV[4],cost)
        redis.call('EXPIRE',KEYS[3],120)
        redis.call('EXPIRE',KEYS[1],120)
        redis.call('INCRBY',KEYS[2],cost);redis.call('EXPIRE',KEYS[2],172800)
        return 0
        """
        async with Redis.from_url(self.redis_url, socket_timeout=3) as redis:
            for _ in range(6):
                wait = await redis.eval(
                    script,
                    3,
                    root + ":rolling:requests",
                    daily,
                    root + ":rolling:costs",
                    self.capacity,
                    amount,
                    self.daily_tokens,
                    member,
                )
                if wait == -1:
                    raise ModelUnavailable("Groq daily allowance reached; retry after reset")
                if wait == 0:
                    return {"daily": daily, "costs": root + ":rolling:costs", "member": member}
                await asyncio.sleep(min(wait, 30))
        raise ModelUnavailable("Groq token allowance is busy; retry the saved step later")

    async def settle(self, daily, reserved, actual):
        delta = actual - reserved
        async with Redis.from_url(self.redis_url, socket_timeout=3) as redis:
            if isinstance(daily, dict):
                script = """
                redis.call('INCRBY',KEYS[1],ARGV[1])
                if redis.call('HEXISTS',KEYS[2],ARGV[2])==1 then
                  redis.call('HINCRBY',KEYS[2],ARGV[2],ARGV[1])
                end
                return 0
                """
                await redis.eval(script, 2, daily["daily"], daily["costs"], delta, daily["member"])
            elif delta:
                # Old in-flight reservations retain their daily accounting semantics.
                await redis.incrby(daily, delta)


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
        output_ticket = (
            await GroqGate(
                self.key,
                self.gate.redis_url,
                tokens_per_minute=950,
                daily_tokens=self.gate.daily_tokens,
            ).reserve(model + ":output", maximum)
            if model.startswith("qwen/")
            else None
        )
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
                    "reasoning_effort": "none" if model.startswith("qwen/") else "low",
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
            if response.status_code == 429:
                raise ModelUnavailable("Groq provider rate limit; retry the saved step later")
            # Do not expose raw provider bodies; errors may echo prompt/account data.
            return httpx.Response(
                response.status_code,
                request=request,
                json={"error": "Groq unavailable or quota/schema rejected"},
            )
        body = response.json()
        usage = body.get("usage", {})
        if not isinstance(usage, dict) or any(
            type(usage.get(k)) is not int or usage[k] < 0
            for k in ("prompt_tokens", "completion_tokens")
        ):
            raise ModelUnavailable("Groq did not return valid measured usage")
        actual = usage["prompt_tokens"] + usage["completion_tokens"]
        await self.gate.settle(daily, amount, actual)
        if output_ticket:
            await self.gate.settle(output_ticket, maximum, usage.get("completion_tokens", 0))
        choice = body["choices"][0]
        # Return known usage even for a truncated answer. Empty content forces the
        # shared schema validator to reject it after accounting for the actual call.
        content = choice["message"].get("content") or ""
        if choice.get("finish_reason") != "stop":
            content = ""
        return httpx.Response(
            200,
            request=request,
            json={
                "message": {"content": content},
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
        gate = gate or GroqGate(
            api_key,
            redis_url or settings.redis_url,
            daily_tokens=settings.groq_daily_token_cap,
        )

        async def record_hosted(metrics):
            if record:
                await record(
                    priced_usage(
                        {
                            **metrics,
                            "provider": "groq",
                            "usd": None,
                            "generation_seconds": None,
                            "cost_basis": "Actual billing not verified; inspect Groq usage",
                        }
                    )
                )

        super().__init__(
            "http://groq-translation",
            config,
            transport=GroqTransport(api_key, gate, upstream=upstream, timeout=config.timeout),
            record=record_hosted,
            **kwargs,
        )
