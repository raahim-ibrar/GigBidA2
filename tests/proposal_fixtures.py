"""Predictable role responses for browser control tests. Never use for quality results."""

from agent.model_client import ModelUnavailable


class BrowserModels:
    outages: set[str] = set()

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
            job = payload["job"]
            if job["title"].startswith("Retry once fixture") and job["job_id"] not in self.outages:
                self.outages.add(job["job_id"])
                raise ModelUnavailable("Deterministic browser model outage; retry to resume.")
            outputs[role] = {"text": "I built a Python API. Could we discuss scope?"}
        if role == "liaison":
            outputs[role] = {
                "intent": "interview"
                if "interview" in payload["client_messages"][-1]["text"].lower()
                else "question",
                "draft": {"text": "I built a Python API. Could we discuss scope?"},
            }
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
