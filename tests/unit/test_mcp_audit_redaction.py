import json

from mcp.types import CallToolResult, TextContent

from agent.mcp_audit import redact_payload


def test_nested_secrets_text_dynamic_keys_and_binary_never_survive():
    payload = {
        "arguments": {
            "request": {"query": "PRIVATE_CV", "k": 5},
            "authorization": "Bearer SECRET",
            "org_uid": "PRIVATE_ORG",
        },
        "structuredContent": {
            "data": {
                "email": "a@example.org",
                "phone": 923001234567,
                "items": [
                    {
                        "id": "PRIVATE_ID",
                        "title": "PRIVATE_NAME",
                        "budget_max": 35,
                        "currency": "USD",
                        "billing_type": "hourly",
                        "synthetic": True,
                    }
                ],
                "a@example.org": {"amount": 123},
                "UNKNOWN_TOKEN_AS_KEY": "SECRET",
            }
        },
        "content": [{"type": "image", "data": "PRIVATE_BASE64", "mimeType": "image/png"}],
    }
    original = json.dumps(payload)
    result = redact_payload(payload)
    assert json.dumps(payload) == original  # Never mutate the actual tool request/result.
    serialized = json.dumps(result)
    assert all(
        s not in serialized
        for s in (
            "PRIVATE",
            "SECRET",
            "a@example.org",
            "923001234567",
            "UNKNOWN_TOKEN_AS_KEY",
        )
    )
    item = result["structuredContent"]["data"]["items"][0]
    assert item["budget_max"] == 35 and item["currency"] == "USD"
    assert result["arguments"]["request"]["k"] == 5


def test_sdk_results_and_json_text_are_redacted_with_bounded_storage():
    result = CallToolResult(
        content=[
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "items": [{"description": "PRIVATE_RESUME", "count": 3}],
                        "access_token": "SECRET",
                    }
                ),
            )
        ],
        isError=True,
    )
    redacted = redact_payload(result)
    assert redacted["isError"] is True
    assert redacted["content"][0]["text"]["redacted_json"]["items"][0]["count"] == 3
    assert "PRIVATE_RESUME" not in repr(redacted) and "SECRET" not in repr(redacted)
    large = {"items": [{"items": ["SECRET" * 100000] * 100}] * 100}
    redacted = redact_payload(large)
    assert len(json.dumps(redacted)) <= 32768 and "truncated" in repr(redacted)
    assert "nan" not in json.dumps(redact_payload({"amount": float("nan")})).lower()


def test_unknown_objects_are_not_stringified():
    class Dangerous:
        def __repr__(self):
            raise AssertionError("Do not stringify arbitrary private objects")

    assert redact_payload(Dangerous()) == "[redacted object]"
