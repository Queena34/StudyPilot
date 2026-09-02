import pytest

from tests.evals.run_faithfulness_sample import (
    DEFAULT_SAMPLE_SIZE,
    _stratified,
)


def _case(case_id: str, tag: str, *, answerable: bool = True) -> dict:
    return {
        "id": case_id,
        "tags": [tag],
        "answerable": answerable,
    }


def test_v2_defaults_to_the_full_thirty_case_review() -> None:
    assert DEFAULT_SAMPLE_SIZE == 30


def test_stratified_sampling_covers_each_stratum_before_repeating() -> None:
    cases = [
        _case("concept-1", "concept"),
        _case("concept-2", "concept"),
        _case("formula-1", "formula"),
        _case("outside-1", "concept", answerable=False),
    ]

    picked = _stratified(cases, 3, seed=7)

    assert {case["stratum"] for case in picked} == {"concept", "formula", "no-answer"}


@pytest.mark.parametrize("size", [0, -1, 3])
def test_stratified_sampling_rejects_an_impossible_size(size: int) -> None:
    cases = [_case("concept-1", "concept"), _case("formula-1", "formula")]

    with pytest.raises(ValueError):
        _stratified(cases, size, seed=7)
