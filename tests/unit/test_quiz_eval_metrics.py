from __future__ import annotations

import json
from pathlib import Path

from tests.evals.quiz_metrics import aggregate_quiz_scores, score_quiz_case


ROOT = Path(__file__).parents[2]


def _case(**overrides):
    case = {
        "id": "quiz-1",
        "document": "notes.pdf",
        "question_type": "single_choice",
        "difficulty": "medium",
        "question_count": 1,
        "page_from": 2,
        "page_to": 4,
        "expected_terms": ["slope"],
        "expected_rejection": False,
    }
    case.update(overrides)
    return case


def _response():
    return {
        "model_name": "test-model",
        "questions": [
            {
                "question_type": "single_choice",
                "difficulty": "medium",
                "content": "关于斜率，哪一项正确？",
                "options": [
                    {"id": "A", "text": "选项 A"},
                    {"id": "B", "text": "选项 B"},
                    {"id": "C", "text": "选项 C"},
                    {"id": "D", "text": "选项 D"},
                ],
                "knowledge_points": ["斜率"],
                "sources": [
                    {
                        "document_id": "doc-1",
                        "filename": "notes.pdf",
                        "page_number": 3,
                        "chunk_id": "chunk-1",
                    }
                ],
            }
        ],
    }


def test_score_valid_quiz_generation() -> None:
    result = score_quiz_case(_case(), _response(), 200)

    assert result["generation_success"] is True
    assert result["question_count_adherence"] is True
    assert result["question_type_adherence"] is True
    assert result["difficulty_adherence"] is True
    assert result["options_format_valid"] is True
    assert result["citation_validity"] is True
    assert result["document_scope_adherence"] is True
    assert result["page_scope_adherence"] is True
    assert result["topic_coverage"] == 1


def test_score_expected_rejection() -> None:
    result = score_quiz_case(
        _case(expected_rejection=True, expected_terms=[]),
        None,
        50,
        "INSUFFICIENT_EVIDENCE",
    )

    assert result["generation_success"] is True
    assert result["rejected"] is True
    assert result["error_code"] == "INSUFFICIENT_EVIDENCE"


def test_aggregate_uses_applicable_denominators() -> None:
    generated = score_quiz_case(_case(), _response(), 200)
    rejected = score_quiz_case(
        _case(id="quiz-2", expected_rejection=True, expected_terms=[]),
        None,
        100,
        "INSUFFICIENT_EVIDENCE",
    )

    metrics = aggregate_quiz_scores([generated, rejected])

    assert metrics["case_count"] == 2
    assert metrics["generated_case_count"] == 1
    assert metrics["rejection_case_count"] == 1
    assert metrics["generation_success_rate"] == 1
    assert metrics["rejection_accuracy"] == 1
    assert metrics["page_scope_adherence"] == 1
    assert metrics["average_latency_ms"] == 150


def test_aggregate_marks_missing_applicable_groups_as_not_available() -> None:
    generated = score_quiz_case(
        _case(page_from=None, page_to=None),
        _response(),
        200,
    )

    metrics = aggregate_quiz_scores([generated])

    assert metrics["rejection_accuracy"] is None
    assert metrics["page_scope_adherence"] is None


def test_unexpected_server_error_is_not_a_correct_rejection() -> None:
    result = score_quiz_case(
        _case(expected_rejection=True, expected_terms=[]),
        None,
        50,
        "INVALID_GENERATED_QUESTIONS",
    )

    assert result["generation_success"] is False


def test_quiz_v1_dataset_contract_and_unmeasured_baseline() -> None:
    dataset = ROOT / "tests/evals/datasets/quiz_generation_v1.jsonl"
    cases = [json.loads(line) for line in dataset.read_text().splitlines() if line]

    assert len(cases) == 30
    assert len({case["id"] for case in cases}) == 30
    assert sum(case["expected_rejection"] for case in cases) == 2
    smoke = [case for case in cases if "smoke" in case["tags"]]
    assert len(smoke) == 3
    assert {case["question_type"] for case in smoke} == {
        "single_choice",
        "short_answer",
        "concept",
    }
    assert {case["difficulty"] for case in smoke} == {"basic", "medium", "advanced"}
    assert {case["question_type"] for case in cases} == {
        "single_choice",
        "short_answer",
        "concept",
    }
    assert {case["difficulty"] for case in cases} == {"basic", "medium", "advanced"}
    assert {case["question_count"] for case in cases} >= {1, 3, 5}

    baseline = json.loads((ROOT / "tests/evals/baselines/quiz_v1.json").read_text())
    assert baseline["status"] == "not_run"
    assert baseline["metrics"] is None
