import json

import httpx
import pytest

from agent.config import AgentConfig
from agent.handoffs import RiskReport
from agent.model_client import ModelUnavailable
from agent.providers.groq import GroqGate, GroqModels


class Gate:
    def __init__(self):
        self.reservations, self.settlements = [], []

    async def reserve(self, model, amount):
        self.reservations.append((model, amount))
        return "fixture-quota"

    async def settle(self, daily, reserved, actual):
        self.settlements.append((daily, reserved, actual))


@pytest.mark.asyncio
async def test_hosted_open_model_preserves_schema_budgets_and_truthful_cost_records():
    config, gate, recorded, calls = AgentConfig(), Gate(), [], []
    config.models = {role: "openai/gpt-oss-120b" for role in config.models}
    config.fallback = None

    async def record(value):
        recorded.append(value)

    def provider(request):
        calls.append(True)
        assert request.url.host == "api.groq.com"
        body = json.loads(request.content)
        assert body["model"] == "openai/gpt-oss-120b"
        assert body["response_format"]["type"] == "json_schema"
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": '{"score":0}'}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    models = GroqModels(
        "unused",
        config,
        api_key="test-only-secret",
        gate=gate,
        upstream=httpx.MockTransport(provider),
        record=record,
    )
    assert (await models.complete("risk", {"job": "fixture"}, RiskReport)).score == 0
    assert len(calls) == 1 and models.tokens == 15
    assert gate.settlements[0][2] == 15
    assert recorded[0]["provider"] == "groq" and recorded[0]["usd"] is None
    assert recorded[0]["estimated_usd"] == 0.0000045
    assert "test-only-secret" not in json.dumps(recorded)


@pytest.mark.asyncio
async def test_provider_error_does_not_echo_credentials_or_response_body():
    config = AgentConfig()
    config.models = {role: "openai/gpt-oss-120b" for role in config.models}
    config.fallback = None
    models = GroqModels(
        "unused",
        config,
        api_key="test-only-secret",
        gate=Gate(),
        upstream=httpx.MockTransport(
            lambda request: httpx.Response(
                429, json={"error": "private account details must not be propagated"}
            )
        ),
    )
    with pytest.raises(ModelUnavailable) as error:
        await models.complete("risk", {}, RiskReport)
    assert "test-only-secret" not in str(error.value)
    assert "private account" not in str(error.value)


async def test_daily_provider_allowance_is_a_retryable_outage(monkeypatch):
    class ExhaustedRedis:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def eval(self, *args):
            return -1

    monkeypatch.setattr(
        "agent.providers.groq.Redis.from_url", lambda *args, **kwargs: ExhaustedRedis()
    )
    gate = GroqGate("test-only-secret", "redis://fixture")
    with pytest.raises(ModelUnavailable, match="daily allowance"):
        await gate.reserve("openai/gpt-oss-120b", 2000)
