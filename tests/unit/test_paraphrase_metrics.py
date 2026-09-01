"""The paraphrase suite scores agreement, not just correctness.

Every message in a group asks for the same thing, so the router giving them
different answers is a defect even when some of those answers are right.
"""

from tests.evals.paraphrase_metrics import (
    aggregate_paraphrase_scores,
    score_paraphrase_case,
)


def _case(group: str, expected: str, supporting: list[str] | None = None) -> dict:
    return {
        "id": f"{group}-x",
        "group": group,
        "message": "…",
        "expected_intent": expected,
        "expected_supporting": supporting or [],
    }


def _decision(intent: str, agent: str, supporting: list[str] | None = None) -> dict:
    return {
        "intent": intent,
        "primary_agent": agent,
        "supporting_agents": supporting or [],
        "source": "rule",
        "target": "rag",
        "latency_ms": 1,
    }


def test_one_group_answered_two_ways_is_inconsistent() -> None:
    scores = [
        score_paraphrase_case(_case("g", "progress_review"), _decision("progress_review", "progress")),
        score_paraphrase_case(_case("g", "progress_review"), _decision("course_qa", "tutor")),
    ]

    metrics = aggregate_paraphrase_scores(scores)

    assert metrics["group_consistency"] == 0.0
    assert metrics["agent_group_consistency"] == 0.0
    assert metrics["by_group"]["g"]["intents_seen"] == ["course_qa", "progress_review"]


def test_labels_that_reach_one_agent_stay_consistent_for_the_learner() -> None:
    """course_qa and concept_explanation both reach the tutor.

    The label disagreement is real and worth seeing, but the learner gets the
    same behaviour, so the two are reported apart.
    """

    scores = [
        score_paraphrase_case(_case("g", "course_qa"), _decision("course_qa", "tutor")),
        score_paraphrase_case(_case("g", "course_qa"), _decision("concept_explanation", "tutor")),
    ]

    metrics = aggregate_paraphrase_scores(scores)

    assert metrics["group_consistency"] == 0.0
    assert metrics["agent_group_consistency"] == 1.0


def test_agreeing_on_the_wrong_answer_is_consistent_but_not_correct() -> None:
    """Consistency alone would reward a router that is uniformly wrong."""

    scores = [
        score_paraphrase_case(_case("g", "study_planning"), _decision("course_qa", "tutor")),
        score_paraphrase_case(_case("g", "study_planning"), _decision("course_qa", "tutor")),
    ]

    metrics = aggregate_paraphrase_scores(scores)

    assert metrics["group_consistency"] == 1.0
    assert metrics["group_full_accuracy"] == 0.0
    assert metrics["intent_accuracy"] == 0.0


def test_a_composite_group_must_agree_on_the_supporting_agents_too() -> None:
    scores = [
        score_paraphrase_case(
            _case("g", "answer_evaluation", ["planner"]),
            _decision("answer_evaluation", "evaluator", ["planner"]),
        ),
        score_paraphrase_case(
            _case("g", "answer_evaluation", ["planner"]),
            _decision("answer_evaluation", "evaluator", []),
        ),
    ]

    metrics = aggregate_paraphrase_scores(scores)

    assert metrics["composite_group_count"] == 1
    assert metrics["composite_group_consistency"] == 0.0
    assert metrics["supporting_accuracy"] == 0.5


def test_the_dataset_groups_several_phrasings_of_each_request() -> None:
    """A group of one cannot disagree with itself, so it measures nothing."""

    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "tests/evals/datasets/router_paraphrase_v1.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    groups: dict[str, int] = {}
    for row in rows:
        groups[row["group"]] = groups.get(row["group"], 0) + 1

    assert len(groups) >= 8
    for name, count in groups.items():
        assert count >= 3, f"{name} 只有 {count} 条说法，无法度量一致性"
