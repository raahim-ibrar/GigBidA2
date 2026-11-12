"""Forty-task tool granularity study: real model predictions, no marketplace effects."""

import argparse
import asyncio
import hashlib
import json
import random
import time
from pathlib import Path

import httpx
from pydantic import Field

from agent.handoffs import Contract
from agent.marketplace_port import MessageWrite, ProposalWrite, SearchJobs
from agent.model_client import BudgetExceeded, ModelUnavailable
from agent.providers.groq import GroqGate
from apps.api.settings import Settings


class ToolCall(Contract):
    name: str = Field(min_length=1)
    arguments: dict


def example_schema(value):
    if isinstance(value, dict):
        return {
            "type": "object",
            "properties": {key: example_schema(item) for key, item in value.items()},
            "required": list(value),
            "additionalProperties": False,
        }
    if type(value) is bool:
        return {"type": "boolean"}
    if type(value) is int:
        return {"type": "integer"}
    return {"type": "string"}


def function_tools(condition):
    result = []
    for tool in tools(condition):
        if condition == "coarse":
            parameters = {
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "enum": tool["operations"]},
                    "payload": {
                        "anyOf": [
                            example_schema(item) for item in tool["payload_structures"].values()
                        ]
                    },
                },
                "required": ["operation", "payload"],
                "additionalProperties": False,
            }
            description = "Call one operation. Payload layouts: " + json.dumps(
                tool["payload_structures"]
            )
        else:
            parameters = example_schema(tool["argument_structure_example"])
            description = tool["description"]
        result.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": description,
                    "parameters": parameters,
                },
            }
        )
    return result


async def predict(model, condition, task, prompt, gate, key):
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": task}],
        "tools": function_tools(condition),
        "tool_choice": "required",
        "parallel_tool_calls": False,
        "temperature": 0,
        "reasoning_effort": "low",
        "max_completion_tokens": 1024,
    }
    reserved = len(json.dumps(payload)) // 3 + 1024
    daily = await gate.reserve(model, reserved)
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": "Bearer " + key},
            json=payload,
        )
    if response.status_code != 200:
        raise ModelUnavailable(f"Groq tool prediction returned HTTP {response.status_code}")
    body = response.json()
    usage = body.get("usage", {})
    tokens = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
    await gate.settle(daily, reserved, tokens)
    choice = body["choices"][0]
    calls = choice["message"].get("tool_calls", [])
    if len(calls) != 1:
        return None, tokens
    function = calls[0]["function"]
    return ToolCall(name=function["name"], arguments=json.loads(function["arguments"])), tokens


def dataset():
    tasks = []
    for i in range(5):
        job, client, conversation, key = (
            f"job-{i}",
            f"client-{i}",
            f"thread-{i}",
            f"request-key-{i}",
        )
        text = f"I would validate milestone {i + 1} before implementation."
        proposal = {
            "job_id": job,
            "text": text,
            "bid_amount": 100 + i,
            "idempotency_key": key,
            "dry_run": True,
        }
        items = [
            (
                "search_jobs",
                {"request": {"query": f"Python API {i}", "limit": 5}},
                f"Search for Python API {i} jobs, returning at most 5 results.",
            ),
            ("get_job", {"job_id": job}, f"Read the full details of job {job}."),
            (
                "get_client_history",
                {"client_id": client},
                f"Inspect {client}'s hiring and payment history.",
            ),
            ("get_connects_balance", {}, "Read my current Connects balance."),
            (
                "list_messages",
                {"conversation_id": conversation},
                f"Read client messages in {conversation}.",
            ),
            (
                "create_proposal_draft",
                {"request": proposal},
                f"Preview, without spending, this proposal: {json.dumps(proposal)}",
            ),
            (
                "submit_proposal",
                {"request": {**proposal, "dry_run": False}},
                "A matching human approval is persisted. Submit this exact approved proposal: "
                + json.dumps({**proposal, "dry_run": False}),
            ),
            (
                "send_message",
                {
                    "request": {
                        "conversation_id": conversation,
                        "text": text,
                        "idempotency_key": key,
                        "dry_run": False,
                    }
                },
                "A matching human approval is already persisted. Send this exact message: "
                + json.dumps(
                    {
                        "conversation_id": conversation,
                        "text": text,
                        "idempotency_key": key,
                        "dry_run": False,
                    }
                ),
            ),
        ]
        for name, arguments, task in items:
            tasks.append(
                {
                    "id": f"tool-{len(tasks):02}",
                    "task": task,
                    "expected": {"name": name, "arguments": arguments},
                }
            )
    return tasks


def tools(condition):
    descriptions = {
        "search_jobs": (
            "Search job listings",
            "Use for discovering jobs by query; not for loading a known job ID.",
        ),
        "get_job": (
            "Get a job",
            "Use for full details of one known job_id; never use client_id here.",
        ),
        "get_client_history": (
            "Get client history",
            "Use for the hiring/payment history of a known client_id.",
        ),
        "get_connects_balance": (
            "Get balance",
            "Read Connects remaining; no arguments and no spending.",
        ),
        "list_messages": (
            "List messages",
            "Read a known conversation_id; never send or modify messages.",
        ),
        "create_proposal_draft": (
            "Create draft",
            "Preview without debit; dry_run true. Use submit_proposal for approved submission.",
        ),
        "submit_proposal": (
            "Submit proposal",
            "Submit the exact approved proposal; dry_run false only with stated approval.",
        ),
        "send_message": (
            "Send message",
            "Send an approved reply with conversation_id, text, idempotency_key and dry_run.",
        ),
    }
    examples = {row["expected"]["name"]: row["expected"]["arguments"] for row in dataset()[:8]}
    if condition == "coarse":
        return [
            {
                "name": "marketplace_read",
                "operations": list(descriptions)[:5],
                "payload_structures": {name: examples[name] for name in list(descriptions)[:5]},
                "arguments": {
                    "operation": "one operation name",
                    "payload": "that operation's fine-tool arguments",
                },
            },
            {
                "name": "marketplace_write",
                "operations": list(descriptions)[5:],
                "payload_structures": {name: examples[name] for name in list(descriptions)[5:]},
                "arguments": {
                    "operation": "one operation name",
                    "payload": "that operation's fine-tool arguments",
                },
            },
        ]
    return [
        {
            "name": name,
            "description": wording[condition == "rewritten"],
            "argument_structure_example": examples[name],
        }
        for name, wording in descriptions.items()
    ]


def logical_call(condition, call):
    if condition == "coarse":
        operation = call.arguments.get("operation")
        reads = set(row["expected"]["name"] for row in dataset()[:5])
        if call.name != ("marketplace_read" if operation in reads else "marketplace_write"):
            return {"name": "invalid", "arguments": {}}
        return {"name": operation, "arguments": call.arguments.get("payload")}
    return call.model_dump()


def canonical(call):
    if not call:
        return None
    schema = {
        "search_jobs": SearchJobs,
        "create_proposal_draft": ProposalWrite,
        "submit_proposal": ProposalWrite,
        "send_message": MessageWrite,
    }.get(call["name"])
    if schema:
        try:
            return {
                "name": call["name"],
                "arguments": {
                    "request": schema.model_validate(call["arguments"]["request"]).model_dump()
                },
            }
        except (ValueError, TypeError, KeyError):
            return {"name": call["name"], "arguments": {"invalid": True}}
    return call


async def run(output, model):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    tasks, conditions = dataset(), ["fine", "coarse", "rewritten"]
    prompt = Path("agent/prompts/experiments/tool_selection.md").read_text(encoding="utf-8")
    plan = {
        "seed": 4016,
        "model": model,
        "output_token_limit": 1024,
        "provider": "groq",
        "protocol": "native function calls; tool_choice required; no effects executed",
        "tasks": tasks,
        "tools": {condition: tools(condition) for condition in conditions},
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "hypothesis": "Rewritten descriptions improve logical tool selection over fine baseline",
        "limits": "Synthetic call predictions; no execution or real-world outcome inference",
    }
    path = output / "plan.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != plan:
        raise ValueError("Frozen tool-study plan differs; choose a new output")
    path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    raw_path = output / "calls.jsonl"
    rows = (
        [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines()]
        if raw_path.exists()
        else []
    )
    done = {(row["condition"], row["id"]) for row in rows}
    settings = Settings()
    key = settings.groq_api_key.get_secret_value()
    gate = GroqGate(key, settings.redis_url)
    for task in tasks:
        order = list(conditions)
        random.Random("4016:" + task["id"]).shuffle(order)
        for condition in order:
            if (condition, task["id"]) in done:
                continue
            tokens = None
            start, result, error = time.perf_counter(), None, None
            try:
                result, tokens = await predict(model, condition, task["task"], prompt, gate, key)
            except ModelUnavailable:
                error = "Provider or schema unavailable"
            except BudgetExceeded:
                raise  # Preserve incomplete coverage, rather than fabricating unattempted calls.
            actual = canonical(logical_call(condition, result)) if result else None
            row = {
                "id": task["id"],
                "condition": condition,
                "prediction": actual,
                "tool_correct": bool(actual and actual["name"] == task["expected"]["name"]),
                "arguments_correct": actual == canonical(task["expected"]),
                "error": error,
                "elapsed_seconds": time.perf_counter() - start,
                "tokens": tokens,
            }
            with raw_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row) + "\n")
            rows.append(row)
            print(
                f"{task['id']} {condition}: "
                f"tool={row['tool_correct']} args={row['arguments_correct']}",
                flush=True,
            )
    summary = {}
    for condition in conditions:
        selected = [row for row in rows if row["condition"] == condition]
        summary[condition] = {
            "n": len(selected),
            "tool_accuracy": sum(row["tool_correct"] for row in selected) / len(selected),
            "argument_accuracy": sum(row["arguments_correct"] for row in selected) / len(selected),
            "tokens_per_task": sum(row["tokens"] or 0 for row in selected) / len(selected),
            "usage_coverage": sum(row["tokens"] is not None for row in selected) / len(selected),
        }
    (output / "results.json").write_text(
        json.dumps(
            {
                "data_origin": "synthetic",
                "model": model,
                "results": summary,
                "complete": len(rows) == 120,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="evals/results/student-tool-study-v3")
    parser.add_argument("--model", default="openai/gpt-oss-120b")
    args = parser.parse_args()
    asyncio.run(run(args.output, args.model))
