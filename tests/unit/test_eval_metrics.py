from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.evals.metrics import aggregate_rag_scores, score_rag_case


ROOT = Path(__file__).parents[2]


def test_score_answerable_case_with_valid_scoped_citation() -> None:
    case = {
        "id": "case-1",
        "answerable": True,
        "document": "notes.pdf",
        "section_contains": "Chapter 1",
        "expected_terms": ["slope", "beta"],
    }
    response = {
        "answer": "The slope is beta one.",
        "citations": [
            {
                "document_id": "doc-1",
                "filename": "notes.pdf",
                "page_number": 2,
                "chunk_id": "chunk-1",
                "section_title": "Chapter 1",
            }
        ],
        "evidence_status": "sufficient",
        "usage": {"model_name": "test-model"},
    }

    result = score_rag_case(case, response, 120)

    assert result["citation_validity"] is True
    assert result["document_scope_adherence"] is True
    assert result["section_scope_adherence"] is True
    assert result["no_answer_correct"] is True
    assert result["keyword_coverage"] == 1


def test_score_no_answer_case_accepts_grounded_refusal_without_citations() -> None:
    case = {
        "id": "case-2",
        "answerable": False,
        "document": "notes.pdf",
        "section_contains": None,
        "expected_terms": [],
    }
    response = {
        "answer": "指定资料中没有找到足够证据。",
        "citations": [],
        "evidence_status": "insufficient",
    }

    result = score_rag_case(case, response, 80)

    assert result["citation_validity"] is True
    assert result["document_scope_adherence"] is True
    assert result["no_answer_correct"] is True


@pytest.mark.parametrize(
    "answer",
    [
        "根据指定资料，没有给出贝叶斯先验选择方法。",
        "指定资料不包含神经网络反向传播算法。",
        "资料完全没有涉及 ARIMA 季节性建模。",
    ],
)
def test_score_no_answer_case_accepts_common_negative_phrases(answer: str) -> None:
    case = {
        "id": "case-negative-phrase",
        "answerable": False,
        "document": "notes.pdf",
        "section_contains": None,
        "expected_terms": [],
    }

    result = score_rag_case(
        case,
        {"answer": answer, "citations": [], "evidence_status": "partial"},
        80,
    )

    assert result["no_answer_correct"] is True
    assert result["no_answer_scored"] is True


def test_keyword_coverage_accepts_chinese_aliases_and_custom_groups() -> None:
    case = {
        "id": "case-bilingual",
        "answerable": True,
        "document": "notes.pdf",
        "section_contains": None,
        "expected_terms": ["error", ["ordinary least squares", "普通最小二乘法"]],
    }
    response = {
        "answer": "误差项可以通过普通最小二乘法进行估计。",
        "citations": [
            {
                "document_id": "doc-1",
                "filename": "notes.pdf",
                "page_number": 1,
                "chunk_id": "chunk-1",
            }
        ],
        "evidence_status": "sufficient",
    }

    result = score_rag_case(case, response, 100)

    assert result["keyword_coverage"] == 1
    assert result["matched_terms"] == ["误差", "普通最小二乘法"]


def test_aggregate_rag_scores() -> None:
    results = [
        {
            "answerable": True,
            "citation_validity": True,
            "document_scope_adherence": True,
            "section_scope_adherence": True,
            "section_scored": True,
            "no_answer_correct": True,
            "no_answer_scored": False,
            "keyword_coverage": 1.0,
            "fallback": False,
            "latency_ms": 100,
        },
        {
            "answerable": False,
            "citation_validity": True,
            "document_scope_adherence": True,
            "section_scope_adherence": True,
            "section_scored": False,
            "no_answer_correct": False,
            "no_answer_scored": True,
            "keyword_coverage": 0.0,
            "fallback": True,
            "latency_ms": 300,
        },
    ]

    metrics = aggregate_rag_scores(results)

    assert metrics["case_count"] == 2
    assert metrics["section_scored_count"] == 1
    assert metrics["no_answer_count"] == 1
    assert metrics["section_scope_adherence"] == 1
    assert metrics["no_answer_accuracy"] == 0
    assert metrics["keyword_coverage"] == 1.0
    assert metrics["fallback_rate"] == 0.5
    assert metrics["average_latency_ms"] == 200


def test_rag_v1_dataset_contract_and_measured_baseline() -> None:
    dataset = ROOT / "tests/evals/datasets/rag_questions_v1.jsonl"
    cases = [json.loads(line) for line in dataset.read_text().splitlines() if line]

    assert len(cases) == 30
    assert len({case["id"] for case in cases}) == 30
    assert sum(not case["answerable"] for case in cases) == 5
    required = {"id", "question", "document", "answerable", "expected_terms", "tags"}
    assert all(required <= case.keys() for case in cases)

    baseline = json.loads((ROOT / "tests/evals/baselines/rag_v1.json").read_text())
    assert baseline["status"] == "measured"
    assert baseline["metrics"]["case_count"] == len(cases)
    assert baseline["model_name"]


def test_aggregate_rejects_empty_results() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        aggregate_rag_scores([])
