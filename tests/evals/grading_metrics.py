from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any


SCORE_BANDS = {
    "correct": (80, 100),
    "partial": (30, 79.99),
    "incorrect": (0, 29.99),
}


def score_grading_run(
    *,
    case: dict[str, Any],
    level: str,
    repeat: int,
    score: float | None,
    evaluation: dict[str, Any] | None,
    model_name: str | None,
    latency_ms: int,
    error: str | None = None,
) -> dict[str, Any]:
    rubric = case["rubric"]
    allowed_evidence = {source["citation_id"] for source in case["sources"]}
    criterion_results = (evaluation or {}).get("criterion_results") or []
    feedback = (evaluation or {}).get("feedback") or {}
    evidence_valid = bool(criterion_results) and all(
        set(item.get("evidence_ids") or []) <= allowed_evidence
        for item in criterion_results
    )
    criterion_complete = (
        len(criterion_results) == len(rubric)
        and {item.get("criterion_index") for item in criterion_results}
        == set(range(len(rubric)))
    )
    feedback_complete = bool(
        str(feedback.get("summary") or "").strip()
        and isinstance(feedback.get("covered_concepts"), list)
        and isinstance(feedback.get("missing_concepts"), list)
        and isinstance(feedback.get("knowledge_errors"), list)
        and isinstance(feedback.get("recommended_topics"), list)
    )
    low, high = SCORE_BANDS[level]
    return {
        "id": f"{case['id']}:{level}:{repeat}",
        "question_id": case["id"],
        "level": level,
        "repeat": repeat,
        "score": score,
        "run_success": error is None and score is not None,
        "score_band_correct": score is not None and low <= score <= high,
        "criterion_complete": criterion_complete,
        "evidence_valid": evidence_valid,
        "feedback_complete": feedback_complete,
        "fallback": model_name == "evaluation-fallback",
        "model_name": model_name,
        "latency_ms": latency_ms,
        "error": error,
    }


def aggregate_grading_scores(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        raise ValueError("results cannot be empty")

    successful = [item for item in results if item["run_success"]]
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    by_question: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for item in successful:
        grouped[(item["question_id"], item["level"])].append(item["score"])
        by_question[item["question_id"]][item["level"]].append(item["score"])

    repeatability = [max(scores) - min(scores) <= 10 for scores in grouped.values()]
    ordering = []
    for levels in by_question.values():
        if all(level in levels for level in ("correct", "partial", "incorrect")):
            ordering.append(
                mean(levels["correct"])
                > mean(levels["partial"])
                > mean(levels["incorrect"])
            )

    def rate(field: str) -> float | None:
        return (
            mean(1.0 if item[field] else 0.0 for item in successful)
            if successful
            else None
        )

    def level_mean(level: str) -> float | None:
        values = [item["score"] for item in successful if item["level"] == level]
        return round(mean(values), 2) if values else None

    return {
        "run_count": len(results),
        "successful_run_count": len(successful),
        "run_success_rate": len(successful) / len(results),
        "score_band_accuracy": rate("score_band_correct"),
        "ordering_accuracy": mean(ordering) if ordering else None,
        "repeatability_within_10_points": mean(repeatability) if repeatability else None,
        "criterion_completeness": rate("criterion_complete"),
        "evidence_validity": rate("evidence_valid"),
        "feedback_completeness": rate("feedback_complete"),
        "fallback_rate": rate("fallback"),
        "average_correct_score": level_mean("correct"),
        "average_partial_score": level_mean("partial"),
        "average_incorrect_score": level_mean("incorrect"),
        "average_latency_ms": round(mean(item["latency_ms"] for item in results), 2),
    }
