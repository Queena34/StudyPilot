import pytest

from tests.evals.faithfulness_metrics import (
    aggregate_faithfulness_scores,
    score_faithfulness_case,
    validate_verdicts,
)


def _case(case_id="c1", *, answerable=True, stratum="concept"):
    return {"id": case_id, "answerable": answerable, "stratum": stratum}


def _verdict(**overrides):
    verdict = {
        "grounding": "supported",
        "citations": "accurate",
        "fabricated": False,
        "admits_gap": False,
    }
    verdict.update(overrides)
    return verdict


def test_a_clean_answer_scores_as_grounded() -> None:
    score = score_faithfulness_case(_case(), _verdict())

    assert score["fully_grounded"] is True
    assert score["any_grounding_problem"] is False
    assert score["citations_accurate"] is True


def test_partial_support_counts_as_a_grounding_problem() -> None:
    score = score_faithfulness_case(_case(), _verdict(grounding="partially_supported"))

    # Partially supported is a problem, not a pass with a caveat.
    assert score["fully_grounded"] is False
    assert score["any_grounding_problem"] is True


def test_an_unanswerable_question_must_be_declined_to_count_as_handled() -> None:
    declined = score_faithfulness_case(_case(answerable=False), _verdict(admits_gap=True))
    answered = score_faithfulness_case(_case(answerable=False), _verdict(admits_gap=False))

    assert declined["correctly_declined"] is True
    assert declined["answered_anyway"] is False
    assert answered["correctly_declined"] is False
    assert answered["answered_anyway"] is True


def test_fabrication_is_tracked_across_every_case() -> None:
    scores = [
        score_faithfulness_case(_case("a"), _verdict()),
        score_faithfulness_case(_case("b"), _verdict(fabricated=True)),
        score_faithfulness_case(_case("c", answerable=False), _verdict(admits_gap=True)),
    ]

    metrics = aggregate_faithfulness_scores(scores)

    # Fabrication is measured over all cases, answerable or not.
    assert metrics["fabrication_rate"] == pytest.approx(1 / 3)


def test_rates_separate_answerable_from_out_of_material_cases() -> None:
    scores = [
        score_faithfulness_case(_case("a"), _verdict()),
        score_faithfulness_case(_case("b"), _verdict(grounding="unsupported")),
        score_faithfulness_case(_case("c", answerable=False), _verdict(admits_gap=True)),
    ]

    metrics = aggregate_faithfulness_scores(scores)

    assert metrics["answerable_case_count"] == 2
    assert metrics["unanswerable_case_count"] == 1
    assert metrics["grounding_rate"] == pytest.approx(0.5)
    assert metrics["declined_when_unsupported_rate"] == 1.0


def test_an_unreviewed_case_blocks_scoring() -> None:
    problems = validate_verdicts([_case("a"), _case("b")], {"a": _verdict()})

    assert any("b" in problem and "未评审" in problem for problem in problems)


def test_a_missing_judgement_blocks_scoring() -> None:
    incomplete = _verdict()
    del incomplete["citations"]

    problems = validate_verdicts([_case("a")], {"a": incomplete})

    # A half-filled sheet reporting 100% would be worse than no review.
    assert any("citations" in problem for problem in problems)


def test_an_out_of_range_judgement_is_rejected() -> None:
    problems = validate_verdicts([_case("a")], {"a": _verdict(grounding="mostly_ok")})

    assert any("grounding" in problem for problem in problems)


def test_a_complete_sheet_passes_validation() -> None:
    assert validate_verdicts([_case("a"), _case("b")], {"a": _verdict(), "b": _verdict()}) == []
