import asyncio
import os
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from agent.providers.groq import GroqGate


@pytest.mark.skipif(
    not os.getenv("GIGBID_TEST_REDIS_URL"), reason="Explicit isolated Redis test URL"
)
async def test_rolling_window_refunds_actual_usage_and_blocks_a_second_burst(monkeypatch):
    url = os.environ["GIGBID_TEST_REDIS_URL"]
    gate = GroqGate("test-only-" + uuid4().hex, url, tokens_per_minute=100, daily_tokens=2000)
    model = "fixture"
    first = await gate.reserve(model, 80)
    await gate.settle(first, 80, 20)
    second = await gate.reserve(model, 60)
    await gate.settle(second, 60, 90)  # Actual usage above estimate must also be accounted.

    async def blocked(seconds):
        assert seconds > 0
        raise asyncio.CancelledError

    monkeypatch.setattr("agent.providers.groq.asyncio.sleep", blocked)
    try:
        with pytest.raises(asyncio.CancelledError):
            await gate.reserve(model, 1)
        async with Redis.from_url(url) as redis:
            assert int(await redis.get(first["daily"])) == 110
    finally:
        async with Redis.from_url(url) as redis:
            await redis.delete(
                first["daily"], first["costs"], first["costs"].replace(":costs", ":requests")
            )
