import json

import pytest
from fastapi.testclient import TestClient

from evals import review_server
from evals.human_review import calibration_items, panel_items
from evals.research_judge import Batch, categorical_agreement, validate_batch


def test_human_packets_are_deterministic_and_blinded():
    rows = calibration_items()
    assert len(rows) == 30 and len({r["id"] for r in rows}) == 30
    assert rows == calibration_items()
    assert all("expected" not in row and "quality" not in row for row in rows)
    pairs, key = panel_items()
    assert len(pairs) == 12 and {r["id"] for r in pairs} == set(key)
    assert "qwen" not in json.dumps(pairs).lower()
    assert all(v["a"] != v["b"] for v in key.values())


def test_missing_or_duplicate_judge_claims_are_rejected():
    items = [{"id": "one", "claims": [{"index": 0}, {"index": 1}]}]
    invalid = Batch.model_validate(
        {
            "items": [
                {
                    "id": "one",
                    "quality": 3,
                    "labels": [{"index": 0, "label": "supported", "reason": "fixture"}],
                }
            ]
        }
    )
    with pytest.raises(ValueError, match="each claim"):
        validate_batch(items, invalid)


def test_categorical_kappa_known_balanced_and_reversed_ratings():
    assert categorical_agreement(["a", "b"], ["a", "b"], ["a", "b"])["kappa"] == 1
    assert categorical_agreement(["a", "b"], ["b", "a"], ["a", "b"])["kappa"] == -1
    assert categorical_agreement([1, 5], [5, 1], [1, 2, 3, 4, 5], weighted=True)["kappa"] == -1
    with pytest.raises(ValueError):
        categorical_agreement(["a"], [], ["a", "b"])


def test_review_server_rejects_cross_origin_and_false_completion(tmp_path, monkeypatch):
    monkeypatch.setattr(review_server, "ROOT", tmp_path)
    directory = tmp_path / "output/reviews"
    directory.mkdir(parents=True)
    (directory / "calibration.json").write_text(
        json.dumps(
            {
                "packet_id": "fixture",
                "items": [{"id": "one"}, {"id": "two"}],
            }
        )
    )
    body = {
        "packet_id": "fixture",
        "reviewer_id": "test-only",
        "kind": "calibration",
        "ratings": [{"id": "one", "support": "supported", "quality": 4}],
        "complete": True,
    }
    with TestClient(review_server.app) as client:
        assert client.post("/api/answers", json=body).status_code == 403
        headers = {"Origin": "http://localhost:8090"}
        assert client.post("/api/answers", json=body, headers=headers).status_code == 422
        body["complete"] = False
        assert client.post("/api/answers", json=body, headers=headers).status_code == 200
        saved = json.loads(
            (tmp_path / "work/human-review/answers/calibration-test-only.json").read_text()
        )
        assert saved["complete"] is False and len(saved["ratings"]) == 1
