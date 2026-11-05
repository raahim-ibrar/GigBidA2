"""Opt-in local inference smoke; neither a quality benchmark nor a model selection."""

import os

import pytest

from agent.config import AgentConfig
from agent.handoffs import JobSpec
from agent.model_client import OllamaModels


@pytest.mark.skipif(os.getenv("GIGBID_REAL_AGENTS") != "1", reason="requires local Ollama models")
async def test_open_model_returns_valid_structured_handoff():
    config = AgentConfig()
    config.fallback = None  # This smoke must exercise the configured model itself.
    records = []

    async def record(value):
        records.append(value)

    models = OllamaModels("http://127.0.0.1:11434", config, record=record)
    result = await models.complete(
        "analyst",
        {
            "job": {
                "job_id": "development-smoke",
                "title": "Python API development",
                "description": "Build a Python REST API with PostgreSQL. Deliver tests and docs.",
                "billing_type": "hourly",
                "budget_min": 20,
                "budget_max": 30,
            },
        },
        JobSpec,
    )
    assert result.requirements
    assert records[0]["model"] == config.models["analyst"]
    assert records[0]["input_tokens"] > 0 and records[0]["output_tokens"] > 0
