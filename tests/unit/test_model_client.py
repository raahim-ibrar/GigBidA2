"""HTTP transport fixtures verify accounting and fallback, not model quality."""

import asyncio
import json

import httpx
import pytest

from agent.config import AgentConfig
from agent.handoffs import Critique, RiskReport
from agent.model_client import BudgetExceeded, ModelUnavailable, OllamaModels
from agent.safety import mask_pii


def reply(content, *, input_tokens=100, output_tokens=20):
    return httpx.Response(
        200,
        json={
            "message": {"content": json.dumps(content)},
            "prompt_eval_count": input_tokens,
            "eval_count": output_tokens,
            "eval_duration": 1000000,
        },
    )


async def test_real_response_usage_is_recorded_without_prompt_content():
    records = []

    async def record(value):
        records.append(value)

    def handler(request):
        body = json.loads(request.content)
        assert body["format"]["type"] == "object"
        assert body["stream"] is False and body["think"] is False
        return reply({"score": 0.2})

    models = OllamaModels(
        "http://fixture", AgentConfig(), record=record, transport=httpx.MockTransport(handler)
    )
    result = await models.complete("risk", {"sensitive": "private input"}, RiskReport)
    assert result.score == 0.2 and models.tokens == 120 and models._reserved == 0
    assert records[0]["input_tokens"] == 100
    assert "private input" not in json.dumps(records)
    assert records[0]["usd"] == 0 and "electricity excluded" in records[0]["cost_basis"]


async def test_cheap_role_fallback_charges_failed_request_conservatively():
    attempted = []

    def handler(request):
        attempted.append(json.loads(request.content)["model"])
        if len(attempted) == 1:
            raise httpx.ConnectError("fixture unavailable")
        return reply({"score": 0})

    config = AgentConfig()
    models = OllamaModels("http://fixture", config, transport=httpx.MockTransport(handler))
    await models.complete("risk", {}, RiskReport)
    assert attempted == [config.models["risk"], config.fallback]
    assert models.tokens > 120 and models._reserved == 0


async def test_critic_does_not_fall_back_to_smaller_model():
    attempted = []

    def handler(request):
        attempted.append(1)
        return httpx.Response(503)

    models = OllamaModels("http://fixture", AgentConfig(), transport=httpx.MockTransport(handler))
    with pytest.raises(ModelUnavailable, match="critic"):
        await models.complete("critic", {}, Critique)
    assert len(attempted) == 1 and models.tokens > 0 and models._reserved == 0


async def test_concurrent_branches_cannot_spend_same_reservation():
    entered, release = asyncio.Event(), asyncio.Event()

    async def handler(request):
        entered.set()
        await release.wait()
        return reply({"score": 0})

    config = AgentConfig()
    config.budgets.max_tokens_per_thread = 3000
    models = OllamaModels("http://fixture", config, transport=httpx.MockTransport(handler))
    running = asyncio.create_task(models.complete("risk", {}, RiskReport))
    await entered.wait()
    try:
        with pytest.raises(BudgetExceeded):
            await models.complete("risk", {}, RiskReport)
    finally:
        release.set()
        await running
    assert models.tokens == 120 and models._reserved == 0


async def test_resumed_token_budget_and_context_are_checked_before_http():
    def handler(request):
        pytest.fail("Budget checks must precede HTTP")

    models = OllamaModels(
        "http://fixture", AgentConfig(), tokens_used=15999, transport=httpx.MockTransport(handler)
    )
    with pytest.raises(BudgetExceeded):
        await models.complete("risk", {}, RiskReport)
    with pytest.raises(BudgetExceeded, match="context"):
        await models.complete("risk", {"job": "a" * 40000}, RiskReport)


async def test_invented_or_missing_usage_is_not_charged_as_free():
    def handler(request):
        return httpx.Response(200, json={"message": {"content": '{"verdict":"pass"}'}})

    models = OllamaModels("http://fixture", AgentConfig(), transport=httpx.MockTransport(handler))
    with pytest.raises(ModelUnavailable):
        await models.complete("critic", {}, Critique)
    assert models.tokens > 0


def test_pii_redaction_is_recursive_and_does_not_mutate_input():
    original = {
        "input_tokens": 123,
        "authorization": "Bearer secret",
        "nested": [
            {"note": "someone@example.com +923001234567", "password": "secret"},
        ],
    }
    masked = mask_pii(original)
    assert masked["authorization"] == "[REDACTED]"
    assert masked["input_tokens"] == 123
    assert masked["nested"][0]["note"] == "[EMAIL] [PHONE]"
    assert masked["nested"][0]["password"] == "[REDACTED]"
    assert original["authorization"] == "Bearer secret"


async def test_durable_reservations_remain_charged_when_inference_is_cancelled():
    charges = []

    async def reserve(amount):
        charges.append(amount)

    async def settle(reserved, charged):
        charges.append(charged - reserved)

    async def handler(request):
        raise asyncio.CancelledError()

    models = OllamaModels(
        "http://fixture",
        AgentConfig(),
        reserve_budget=reserve,
        settle_budget=settle,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(asyncio.CancelledError):
        await models.complete("risk", {}, RiskReport)
    assert sum(charges) == models.tokens > 0 and models._reserved == 0
