import pytest

from evals.fidelity_analysis import require_matched, validate_outcomes
from evals.fidelity_clients import client_payload


def test_matched_jobs_reject_missing_or_duplicate_members():
    require_matched({"v0": ["a", "b"], "v3": ["b", "a"]})
    with pytest.raises(ValueError):
        require_matched({"v0": ["a", "b"], "v3": ["a"]})
    with pytest.raises(ValueError):
        require_matched({"v0": ["a", "a"], "v3": ["a"]})


def test_pending_client_or_changed_submission_is_never_a_negative_label():
    source = [{"group": "rag", "condition": "v0", "id": "job", "outcome": {"submitted": True}}]
    pending = {
        "group": "rag",
        "condition": "v0",
        "id": "job",
        "submitted": True,
        "client_model_called": False,
        "followup_complete": False,
    }
    with pytest.raises(ValueError):
        validate_outcomes(source, [])
    with pytest.raises(ValueError):
        validate_outcomes(source, [pending])
    with pytest.raises(ValueError):
        validate_outcomes(source, [{**pending, "submitted": False, "followup_complete": True}])
    validate_outcomes(source, [{**pending, "client_model_called": True, "followup_complete": True}])


def test_client_payload_excludes_gold_condition_and_portfolio_bodies():
    row = {
        "id": "synthetic-job",
        "opaque_id": "opaque",
        "condition": "private-variant",
        "candidate": {"text": "I would build the API.", "price": 30},
        "snapshot": {},
        "evidence": [{"text": "PRIVATE_EVIDENCE_CANARY"}],
    }
    job = {
        "title": "API",
        "description": "Build an API",
        "required_skills": ["Python"],
        "budget_min": 20,
        "budget_max": 40,
        "screening_questions": [],
        "gold": {"bid": True},
        "source": "private-source",
    }
    payload = client_payload(row, job)
    assert "PRIVATE_EVIDENCE_CANARY" not in str(payload)
    assert "private-variant" not in str(payload) and "gold" not in str(payload)
    assert payload["id"] == "opaque"
