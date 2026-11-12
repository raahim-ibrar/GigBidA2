from collections import deque

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import PrivateAttr

from agent.config import AgentConfig
from agent.handoffs import EvidenceItem
from agent.model_client import BudgetExceeded
from apps.api.settings import Settings

pytest.importorskip("langchain_openai", reason="Install the optional research dependencies")
pytest.importorskip("langgraph_supervisor", reason="Install the optional research dependencies")

from evals.research_architectures import run_native  # noqa: E402
from evals.research_client import (  # noqa: E402
    RequiredToolsChat,
    ResearchBudget,
    normalized_failed_call,
)


class ScriptedChat(BaseChatModel):
    _answers: deque = PrivateAttr()

    def __init__(self, answers):
        super().__init__()
        self._answers = deque(answers)

    @property
    def _llm_type(self):
        return "test-only-scripted-chat"

    def bind_tools(self, tools, **kwargs):
        return self.bind(tools=[convert_to_openai_tool(t) for t in tools])

    def _generate(self, *args, **kwargs):
        raise AssertionError("Only async inference is expected")

    async def _agenerate(self, messages, **kwargs):
        assert self._answers, "Unexpected extra inference call"
        return ChatResult(generations=[ChatGeneration(message=self._answers.popleft())])


def call(name, arguments=None):
    return AIMessage(
        content="",
        tool_calls=[
            {
                "id": name + "-fixture",
                "name": name,
                "args": arguments or {},
                "type": "tool_call",
            }
        ],
    )


class Client:
    async def aclose(self):
        pass


class Portfolio:
    async def search(self, *args, **kwargs):
        return [
            EvidenceItem(
                id="fixture",
                text="Fictional Python API prototype.",
                source="case.md",
                type="case_study",
            )
        ]


class Market:
    async def job(self, identity):
        return {"id": identity, "title": "Python API", "description": "Build an API"}


@pytest.mark.parametrize("kind", ["react", "supervisor"])
async def test_native_graphs_can_finalize_and_supervisor_terminates(monkeypatch, kind):
    candidate = {
        "action": "bid",
        "risk_score": 0,
        "reasons": ["Python evidence"],
        "price": 30,
        "text": "I would clarify the API endpoints and add validation.",
        "screening_answers": {},
    }
    reads = [call("get_job"), call("search_evidence", {"query": "Python API"})]
    if kind == "react":
        answers = [*reads, call("finalize_candidate", candidate)]
    else:
        answers = [
            call("transfer_to_analyst"),
            *reads,
            call("report_analysis", {"summary": "Python API fits the fictional evidence."}),
            call("transfer_to_writer"),
            call("finalize_candidate", candidate),
            call("finish_research"),
        ]
    model = ScriptedChat(answers)
    monkeypatch.setattr(
        "evals.research_architectures.native_model",
        lambda *args: (model, Client(), ResearchBudget()),
    )
    got, _, calls = await run_native(
        kind,
        Settings(),
        "fixture",
        AgentConfig(),
        {"id": "job", "title": "Python API"},
        Portfolio(),
        Market(),
        "problem_first",
    )
    assert got.action == "bid" and not model._answers
    assert "finalize_candidate" in calls
    if kind == "supervisor":
        assert calls[-1] == "finish_research" and "report_analysis" in calls


async def test_one_budget_covers_parallel_native_and_verifier_calls():
    budget = ResearchBudget(100)
    await budget.reserve(70)
    with pytest.raises(BudgetExceeded):
        await budget.reserve(40)
    await budget.settle(70, 20)
    await budget.reserve(80)
    await budget.settle(80, 30)
    assert budget.used == 50 and budget.reserved == 0


def test_native_model_requires_tool_calls_instead_of_unparseable_free_text():
    model = RequiredToolsChat(model="fixture", api_key="test-only-key")
    bound = model.bind_tools(
        [
            {
                "type": "function",
                "function": {
                    "name": "finish",
                    "description": "Finish",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
    )
    assert bound.kwargs["tool_choice"] == "required"


def test_transport_name_normalization_cannot_add_tools_or_invent_arguments():
    import json

    body = {"tools": [{"type": "function", "function": {"name": "finalize_candidate"}}]}
    arguments = {"action": "bid", "text": "A fictional candidate"}
    error = {
        "code": "tool_use_failed",
        "failed_generation": json.dumps(
            {
                "name": "to=functions.finalize_candidate<|channel|>commentary",
                "arguments": arguments,
            }
        ),
    }
    got = normalized_failed_call(body, error)
    assert got["function"]["name"] == "finalize_candidate"
    assert json.loads(got["function"]["arguments"]) == arguments
    error["failed_generation"] = json.dumps({"name": "to=functions.delete_all", "arguments": {}})
    assert normalized_failed_call(body, error) is None
    assert normalized_failed_call(body, {"code": "output_parse_failed"}) is None
