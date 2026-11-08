import json
import math

import pytest
from pydantic import ValidationError

from evals.contracts import GoldJob, Outcome, Prediction
from evals.io import read_rows, write_result
from evals.metrics import classification, cohen_kappa, retrieval
from evals.runners.suite import evaluate_bundle
from evals.scoring import decision_scores, rag_scores


def test_confusion_matrix_and_undefined_labels():
    result = classification([True, True, False, False], [True, False, True, False])
    assert result["tp"] == result["fp"] == result["tn"] == result["fn"] == 1
    assert result["f1"] == result["accuracy"] == 0.5
    assert classification([False], [False])["f1"] is None
    with pytest.raises(ValueError):
        classification([True], [])
    with pytest.raises(ValueError):
        classification([1], [True])


def test_retrieval_ranking_and_no_answer_cases():
    score = retrieval(["a", "b"], ["x", "a", "b"], 2)
    assert score["recall"] == score["precision"] == score["mrr"] == 0.5
    assert score["ndcg"] == pytest.approx((1 / math.log2(3)) / (1 + 1 / math.log2(3)))
    assert retrieval([], ["x"], 5)["recall"] is None
    with pytest.raises(ValueError):
        retrieval(["a"], ["a", "a"], 5)


def test_job_alignment_missing_outputs_and_annotation_coverage():
    gold = [GoldJob(id="a", persona="fixture", bid=True, scam=False, relevant_ids=["source"])]
    prediction = Prediction(id="a", bid=True, scam=False, ranked_ids=["source"])
    assert rag_scores(gold, [prediction])["overall"]["macro_recall_at_k"] == 1
    result = decision_scores(gold, [prediction])["overall"]
    assert result["unsupported_claim_rate"] is None and not result["claim_annotations_complete"]
    labelled = prediction.model_copy(
        update={"claim_labels": ["supported", "ambiguous"], "claim_label_source": "human-fixture"}
    )
    assert decision_scores(gold, [labelled])["overall"]["unsupported_claim_rate"] == 0.5
    with pytest.raises(ValueError, match="match exactly"):
        rag_scores(gold, [prediction.model_copy(update={"id": "different"})])
    with pytest.raises(ValueError, match="Missing ranked"):
        rag_scores(gold, [prediction.model_copy(update={"ranked_ids": None})])


def test_kappa_known_agreement_and_degenerate_case():
    assert cohen_kappa([True, True, False, False], [True, False, True, False])["kappa"] == 0
    assert cohen_kappa([True, False], [True, False])["kappa"] == 1
    assert cohen_kappa([True], [True])["kappa"] is None


def test_invalid_data_never_creates_a_report(tmp_path):
    source = tmp_path / "fixture.jsonl"
    source.write_text('{"id":"same","persona":"fixture","bid":true,"scam":false}\n' * 2)
    with pytest.raises(ValueError, match="unique"):
        read_rows(source, GoldJob)
    with pytest.raises(ValidationError):
        Prediction(id="a", bid="true")
    with pytest.raises(ValidationError):
        Prediction(id="a", claim_labels=["supported"])
    with pytest.raises(ValidationError):
        Outcome(id="a", event_id="e", source="gigsim", submitted=False, replied=True, hired=False)
    with pytest.raises(ValueError, match="overwrite"):
        write_result(
            source, metric="fixture", data_origin="development", inputs={source: {}}, results={}
        )
    target = tmp_path / "result.json"
    write_result(
        target,
        metric="fixture",
        data_origin="development",
        inputs={source: {"sha256": "fixture"}},
        results={"n": 2},
    )
    report = json.loads(target.read_text())
    assert report["data_origin"] == "development" and report["inputs"][0]["sha256"] == "fixture"


def test_full_gate_requires_complete_observations_and_keeps_development_provenance(tmp_path):
    personas = ["ai_ml", "full_stack", "data_analyst"]
    gold, predictions, outcomes = [], [], []
    for index in range(30):
        id = str(index)
        gold.append(
            {
                "id": id,
                "persona": personas[index % 3],
                "bid": True,
                "scam": False,
                "relevant_ids": ["source"],
            }
        )
        predictions.append(
            {
                "id": id,
                "bid": True,
                "scam": False,
                "ranked_ids": ["source"],
                "claim_labels": ["supported"],
                "claim_label_source": "unit-fixture",
            }
        )
        outcomes.append(
            {
                "id": id,
                "event_id": "fixture-" + id,
                "source": "gigsim",
                "submitted": True,
                "followup_complete": True,
                "replied": index % 2 == 0,
                "hired": False,
                "connects": 8,
            }
        )
    for name, rows in (("gold", gold), ("predictions", predictions), ("outcomes", outcomes)):
        (tmp_path / f"{name}.jsonl").write_text("\n".join(json.dumps(row) for row in rows))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "data_origin": "development",
                "experiment_id": "unit-fixture",
                "gold": "gold.jsonl",
                "predictions": "predictions.jsonl",
                "outcomes": "outcomes.jsonl",
                "bid_f1_floor": 0.8,
                "unsupported_claim_rate_ceiling": 0.02,
            }
        )
    )
    with pytest.raises(ValueError, match="requires supplied"):
        evaluate_bundle(manifest, tmp_path / "blocked", require_supplied=True)
    report = evaluate_bundle(manifest, tmp_path / "results")
    assert report["results"]["passed"] and report["data_origin"] == "development"
    predictions[0]["claim_labels"] = None
    (tmp_path / "predictions.jsonl").write_text("\n".join(json.dumps(row) for row in predictions))
    failed = evaluate_bundle(manifest, tmp_path / "failed")
    assert not failed["results"]["passed"]
    assert not failed["results"]["checks"]["unsupported_claim_rate"]
