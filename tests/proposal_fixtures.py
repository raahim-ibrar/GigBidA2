"""Predictable role responses for browser control tests. Never use for quality results."""


class BrowserModels:
    def __init__(self, *args, **kwargs):
        pass

    async def complete(self, role, payload, schema):
        outputs = {
            "analyst": {
                "job_id": "browser-fixture",
                "title": "Fixture",
                "requirements": ["Python"],
            },
            "risk": {"score": 0},
            "critic": {"verdict": "pass"},
        }
        if role == "matcher":
            outputs[role] = {
                "requirement_evidence": {
                    key: [item["id"] for item in payload["evidence"]]
                    for key in payload["requirements"]
                }
            }
        if role == "writer":
            outputs[role] = {"text": "I built a Python API. Could we discuss scope?"}
        if role == "verifier":
            outputs[role] = {
                "claims": [
                    {
                        "index": item["index"],
                        "kind": "experience" if "built" in item["text"] else "non_experience",
                        "verdict": "supported",
                        "evidence_ids": [item["id"] for item in payload["evidence"]],
                        "reason": "Deterministic browser fixture",
                    }
                    for item in payload["sentences"]
                ]
            }
        return schema.model_validate(outputs[role])
