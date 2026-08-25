import pytest

from app.core.exceptions import AppError
from app.domain.models import Question
from app.llm.evaluation_gateway import _fallback_evaluation
from app.services.attempt_service import _evaluate_single_choice, _score_evaluation


def _question() -> Question:
    return Question(
        question_type="single_choice",
        difficulty="basic",
        content="Which is correct?",
        options_json=[
            {"id": "A", "text": "Correct", "is_correct": True},
            {"id": "B", "text": "Wrong", "is_correct": False},
        ],
        knowledge_points_json=["Regularization"],
        reference_answer="Correct",
        rubric_json=[
            {
                "criterion": "Choose the supported answer",
                "weight": 1.0,
                "required_concepts": ["Regularization"],
                "evidence_ids": ["c1"],
            }
        ],
        source_refs_json=[{"citation_id": "c1"}],
        generation_metadata_json={},
    )


def test_single_choice_is_graded_deterministically() -> None:
    evaluation, model = _evaluate_single_choice(_question(), "a")
    results, score = _score_evaluation(
        evaluation,
        _question().rubric_json,
        _question().source_refs_json,
    )

    assert model == "deterministic-choice-grader"
    assert score == 100
    assert results[0].points == 100


def test_single_choice_rejects_unknown_option() -> None:
    with pytest.raises(AppError) as exc_info:
        _evaluate_single_choice(_question(), "Z")

    assert exc_info.value.code == "INVALID_OPTION"


def test_fallback_evaluation_is_stable_and_bounded() -> None:
    rubric = [
        {
            "criterion": "Explain regularization",
            "weight": 1.0,
            "required_concepts": ["regularization"],
            "evidence_ids": ["c1"],
        }
    ]

    first = _fallback_evaluation(
        "Regularization limits model complexity.",
        "Regularization limits model complexity and reduces overfitting.",
        rubric,
    )
    second = _fallback_evaluation(
        "Regularization limits model complexity.",
        "Regularization limits model complexity and reduces overfitting.",
        rubric,
    )

    assert first == second
    assert 0 <= first.criterion_results[0].earned_ratio <= 1


def test_scoring_rejects_unknown_evidence() -> None:
    evaluation, _ = _evaluate_single_choice(_question(), "A")
    evaluation.criterion_results[0].evidence_ids = ["c9"]

    with pytest.raises(AppError) as exc_info:
        _score_evaluation(
            evaluation,
            _question().rubric_json,
            _question().source_refs_json,
        )

    assert exc_info.value.code == "INVALID_EVALUATION_CITATION"
