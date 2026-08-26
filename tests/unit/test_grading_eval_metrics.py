from __future__ import annotations

import json
from pathlib import Path

from tests.evals.grading_metrics import aggregate_grading_scores, score_grading_run


ROOT = Path(__file__).parents[2]


def _case():
    return {
        "id": "grade-test",
        "rubric": [
            {"criterion": "concept", "weight": 1.0, "evidence_ids": ["c1"]}
        ],
        "sources": [{"citation_id": "c1"}],
    }


def _evaluation():
    return {
        "criterion_results": [
            {"criterion_index": 0, "earned_ratio": 1, "evidence_ids": ["c1"]}
        ],
        "feedback": {
            "summary": "Good",
            "covered_concepts": ["concept"],
            "missing_concepts": [],
            "knowledge_errors": [],
            "recommended_topics": [],
        },
    }


def test_score_successful_correct_answer_run() -> None:
    result = score_grading_run(
        case=_case(),
        level="correct",
        repeat=1,
        score=95,
        evaluation=_evaluation(),
        model_name="test-model",
        latency_ms=100,
    )

    assert result["run_success"] is True
    assert result["score_band_correct"] is True
    assert result["criterion_complete"] is True
    assert result["evidence_valid"] is True
    assert result["feedback_complete"] is True


def test_aggregate_grading_ordering_and_repeatability() -> None:
    results = []
    for level, scores in {
        "correct": [95, 90, 92],
        "partial": [60, 65, 62],
        "incorrect": [5, 10, 8],
    }.items():
        for repeat, score in enumerate(scores, 1):
            results.append(
                score_grading_run(
                    case=_case(),
                    level=level,
                    repeat=repeat,
                    score=score,
                    evaluation=_evaluation(),
                    model_name="test-model",
                    latency_ms=100,
                )
            )

    metrics = aggregate_grading_scores(results)

    assert metrics["run_count"] == 9
    assert metrics["ordering_accuracy"] == 1
    assert metrics["repeatability_within_10_points"] == 1
    assert metrics["score_band_accuracy"] == 1
    assert metrics["fallback_rate"] == 0


def test_grading_v1_dataset_contract_and_recorded_baseline() -> None:
    dataset = ROOT / "tests/evals/datasets/grading_answers_v1.jsonl"
    cases = [json.loads(line) for line in dataset.read_text().splitlines() if line]

    assert len(cases) == 10
    assert len({case["id"] for case in cases}) == 10
    assert all(set(case["answers"]) == {"correct", "partial", "incorrect"} for case in cases)
    assert all(abs(sum(item["weight"] for item in case["rubric"]) - 1) < 0.001 for case in cases)
    assert all(case["sources"] for case in cases)

    baseline = json.loads((ROOT / "tests/evals/baselines/grading_v1.json").read_text())
    assert baseline["status"] == "recorded"
    assert baseline["configuration"]["total_runs"] == 90
    metrics = baseline["metrics"]
    # A baseline may only be claimed once every run completed without falling back.
    assert metrics["run_count"] == 90
    assert metrics["run_success_rate"] == 1.0
    assert metrics["fallback_rate"] == 0.0
    # Ordering is the floor for a usable grader and is a hard gate in the baseline.
    assert metrics["ordering_accuracy"] == 1
    assert metrics["repeatability_within_10_points"] == 1
    # Any deviation must stay diagnosed rather than merely recorded.
    assert len(baseline["out_of_band_runs"]) == round(
        (1 - metrics["score_band_accuracy"]) * metrics["run_count"]
    )
    assert baseline["diagnosis"] and baseline["regression_rules"]
