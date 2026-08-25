from app.infrastructure.repositories.progress_repository import (
    _mastery_score,
    _mastery_status,
    _merge_errors,
    _normalize_topic,
)


def test_topic_normalization_is_case_and_space_insensitive() -> None:
    assert _normalize_topic("  L1   Regularization ") == "l1 regularization"


def test_mastery_requires_repeated_success_before_mastered() -> None:
    first_score = _mastery_score(100, 100, 1)
    second_score = _mastery_score(100, 100, 2)

    assert _mastery_status(first_score, 1) == "learning"
    assert _mastery_status(second_score, 2) == "mastered"


def test_low_score_marks_topic_weak() -> None:
    score = _mastery_score(0, 0, 1)

    assert score < 0.5
    assert _mastery_status(score, 1) == "weak"


def test_common_errors_are_counted_and_bounded() -> None:
    merged = _merge_errors({"missing definition": 1}, ["missing definition", "wrong example"])

    assert merged["missing definition"] == 2
    assert merged["wrong example"] == 1
