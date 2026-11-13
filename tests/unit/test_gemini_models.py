import json

import httpx
import pytest

from agent.config import AgentConfig
from agent.handoffs import RiskReport
from agent.model_client import ModelUnavailable
from agent.providers.gemini import ENDPOINT, GeminiChatTransport, GeminiModels


class Gate:
    async def reserve(self, model):
        assert model in {"gemini-3.1-flash-lite", "gemini-3.5-flash-lite"}


async def test_gemini_schema_handoff_and_usage_remain_validated_without_logging_key():
    recorded = []

    async def record(row):
        recorded.append(row)

    def provider(request):
        assert request.url.host == "generativelanguage.googleapis.com"
        body = json.loads(request.content)
        assert body["response_format"]["type"] == "json_schema"
        assert body["reasoning_effort"] == "minimal"
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": '{"score":0}'}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    model = GeminiModels(
        "unused",
        AgentConfig(profile_name="paid"),
        api_key="test-secret",
        gate=Gate(),
        upstream=httpx.MockTransport(provider),
        record=record,
    )
    assert (await model.complete("risk", {"job": "fictional"}, RiskReport)).score == 0
    assert model.tokens == 15 and recorded[0]["provider"] == "gemini"
    assert recorded[0]["usd"] is None and "test-secret" not in json.dumps(recorded)
    assert recorded[0]["estimated_usd"] == 0.00001


async def test_hidden_transient_retries_are_reported_as_unknown_cost(monkeypatch):
    recorded, attempts = [], []

    async def record(row):
        recorded.append(row)

    async def no_sleep(seconds):
        pass

    monkeypatch.setattr("agent.providers.gemini.asyncio.sleep", no_sleep)

    def provider(request):
        attempts.append(True)
        if len(attempts) == 1:
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": '{"score":0}'}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    model = GeminiModels(
        "unused",
        AgentConfig(profile_name="paid"),
        api_key="test-secret",
        gate=Gate(),
        upstream=httpx.MockTransport(provider),
        record=record,
    )
    await model.complete("risk", {}, RiskReport)
    assert len(recorded) == 2 and recorded[0]["estimated_usd"] is None
    assert recorded[0]["role"] == "transport_retry" and recorded[1]["estimated_usd"] == 0.00001


async def test_multi_turn_tool_signature_survives_client_normalization():
    count = 0

    def provider(request):
        nonlocal count
        count += 1
        body = json.loads(request.content)
        if count == 1:
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-fixture",
                        "type": "function",
                        "function": {"name": "read", "arguments": "{}"},
                        "extra_content": {"google": {"thought_signature": "opaque-fixture"}},
                    }
                ],
            }
            finish = "tool_calls"
        else:
            extra = body["messages"][0]["tool_calls"][0]["extra_content"]
            assert extra == {"google": {"thought_signature": "opaque-fixture"}}
            assert body["max_tokens"] == 100 and "max_completion_tokens" not in body
            message, finish = {"role": "assistant", "content": "done"}, "stop"
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": finish, "message": message}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    records = []
    transport = GeminiChatTransport(
        "test-secret", Gate(), records=records, upstream=httpx.MockTransport(provider)
    )
    await transport.handle_async_request(
        httpx.Request(
            "POST",
            ENDPOINT,
            json={
                "model": "gemini-3.5-flash-lite",
                "messages": [],
                "max_tokens": 100,
            },
        )
    )
    await transport.handle_async_request(
        httpx.Request(
            "POST",
            ENDPOINT,
            json={
                "model": "gemini-3.5-flash-lite",
                "max_completion_tokens": 100,
                "messages": [
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": "call-fixture",
                                "type": "function",
                                "function": {"name": "read", "arguments": "{}"},
                            }
                        ],
                    }
                ],
            },
        )
    )
    assert count == 2 and len(records) == 2
    assert "opaque-fixture" not in json.dumps(records)


async def test_gemini_rate_limit_is_retryable_and_does_not_echo_provider_body():
    transport = GeminiChatTransport(
        "test-secret",
        Gate(),
        upstream=httpx.MockTransport(
            lambda request: httpx.Response(
                429, json={"error": {"message": "private-provider-details"}}
            )
        ),
    )
    with pytest.raises(ModelUnavailable, match="rate limit") as caught:
        await transport.handle_async_request(
            httpx.Request(
                "POST",
                ENDPOINT,
                json={
                    "model": "gemini-3.5-flash-lite",
                    "messages": [],
                    "max_tokens": 100,
                },
            )
        )
    assert "private-provider-details" not in str(caught.value)
    assert "test-secret" not in str(caught.value)


async def test_gemini_retries_temporary_outage_without_losing_tool_request(monkeypatch):
    attempts = 0

    async def no_wait(seconds):
        pass

    monkeypatch.setattr("agent.providers.gemini.asyncio.sleep", no_wait)

    def provider(request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, json={"error": {"message": "high demand"}})
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    from evals.research_client import ResearchBudget

    budget = ResearchBudget(1000)
    records = []
    transport = GeminiChatTransport(
        "test-secret",
        Gate(),
        upstream=httpx.MockTransport(provider),
        budget=budget,
        records=records,
    )
    result = await transport.handle_async_request(
        httpx.Request(
            "POST",
            ENDPOINT,
            json={"model": "gemini-3.5-flash-lite", "max_tokens": 100, "messages": []},
        )
    )
    assert result.status_code == 200 and attempts == 2
    assert budget.reserved == 0 and budget.used > 15
    assert records[0]["status"] == 503 and records[1]["status"] == 200
