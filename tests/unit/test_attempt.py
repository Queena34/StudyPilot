import pytest

from app.core.exceptions import AppError
from app.domain.models import Question
from app.llm.evaluation_gateway import _fallback_evaluation
from app.services.attempt_service import (
    _evaluate_multiple_choice,
    _evaluate_single_choice,
    _score_evaluation,
)


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


def _multi_question() -> Question:
    question = _question()
    question.question_type = "multiple_choice"
    question.options_json = [
        {"id": "A", "text": "Correct", "is_correct": True},
        {"id": "B", "text": "Also correct", "is_correct": True},
        {"id": "C", "text": "Wrong", "is_correct": False},
        {"id": "D", "text": "Also wrong", "is_correct": False},
    ]
    return question


def _multi_score(answer: str) -> float:
    evaluation, _ = _evaluate_multiple_choice(_multi_question(), answer)
    question = _multi_question()
    _, score = _score_evaluation(evaluation, question.rubric_json, question.source_refs_json)
    return score


def test_every_answer_earns_full_marks() -> None:
    assert _multi_score("A,B") == 100.0
    assert _multi_score("b, a") == 100.0


def test_a_missing_answer_still_earns_its_share() -> None:
    assert _multi_score("A") == 50.0


def test_a_wrong_pick_gives_back_what_a_right_one_earned() -> None:
    # Selecting everything must not score as if the learner knew the answer.
    assert _multi_score("A,B,C,D") == 0.0
    assert _multi_score("A,B,C") == 50.0


def test_only_wrong_picks_score_nothing() -> None:
    assert _multi_score("C,D") == 0.0


def test_an_option_outside_the_question_is_rejected() -> None:
    with pytest.raises(AppError) as error:
        _evaluate_multiple_choice(_multi_question(), "A,Z")
    assert error.value.code == "INVALID_OPTION"


def test_an_empty_selection_is_rejected() -> None:
    with pytest.raises(AppError) as error:
        _evaluate_multiple_choice(_multi_question(), ",")
    assert error.value.code == "INVALID_OPTION"
