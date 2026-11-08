import pytest

from evals.experiments import analyse_arms, assign_arms, fisher_exact


def test_assignment_is_order_independent_and_balanced_within_strata():
    jobs = [
        {"id": str(index), "persona": "fixture", "category": str(index % 3)} for index in range(21)
    ]
    assigned = assign_arms(jobs, 4016)
    assert assigned == assign_arms(list(reversed(jobs)), 4016)
    for category in ("0", "1", "2"):
        arms = [assigned[item["id"]] for item in jobs if item["category"] == category]
        assert abs(arms.count("evidence_first") - arms.count("problem_first")) <= 1


def test_fisher_known_table_symmetry_and_degenerate_outcomes():
    assert fisher_exact(1, 10, 11, 14) == pytest.approx(0.0027594561852200836)
    assert fisher_exact(1, 10, 11, 14) == fisher_exact(11, 14, 1, 10)
    assert fisher_exact(0, 10, 0, 10) == 1
    with pytest.raises(ValueError):
        fisher_exact(1, 0, 1, 2)


def test_analysis_requires_complete_cohort_and_reports_conservative_interval():
    assigned = {"a": "evidence_first", "b": "problem_first"}
    observed = [
        {"id": "a", "replied": True, "followup_complete": True},
        {"id": "b", "replied": False, "followup_complete": True},
    ]
    result = analyse_arms(assigned, observed)
    assert result["difference_evidence_minus_problem"] == 1
    assert result["difference_interval"] == [-1, 1]
    assert result["fisher_two_sided_p"] == 1
    with pytest.raises(ValueError, match="Every assigned"):
        analyse_arms(assigned, observed[:1])
    with pytest.raises(ValueError, match="complete"):
        analyse_arms(assigned, [{**row, "followup_complete": False} for row in observed])
