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


def test_aggregate_rag_scores() -> None:
    results = [
        {
            "answerable": True,
            "citation_validity": True,
            "document_scope_adherence": True,
            "section_scope_adherence": True,
            "no_answer_correct": True,
            "keyword_coverage": 1.0,
            "fallback": False,
            "latency_ms": 100,
        },
        {
            "answerable": False,
            "citation_validity": True,
            "document_scope_adherence": True,
            "section_scope_adherence": True,
            "no_answer_correct": False,
            "keyword_coverage": 0.0,
            "fallback": True,
            "latency_ms": 300,
        },
    ]

    metrics = aggregate_rag_scores(results)

    assert metrics["case_count"] == 2
    assert metrics["no_answer_accuracy"] == 0.5
    assert metrics["keyword_coverage"] == 1.0
    assert metrics["fallback_rate"] == 0.5
    assert metrics["average_latency_ms"] == 200


def test_rag_v1_dataset_contract_and_unmeasured_baseline() -> None:
    dataset = ROOT / "tests/evals/datasets/rag_questions_v1.jsonl"
    cases = [json.loads(line) for line in dataset.read_text().splitlines() if line]

    assert len(cases) == 30
    assert len({case["id"] for case in cases}) == 30
    assert sum(not case["answerable"] for case in cases) == 5
    required = {"id", "question", "document", "answerable", "expected_terms", "tags"}
    assert all(required <= case.keys() for case in cases)

    baseline = json.loads((ROOT / "tests/evals/baselines/rag_v1.json").read_text())
    assert baseline["status"] == "not_run"
    assert baseline["metrics"] is None


def test_aggregate_rejects_empty_results() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        aggregate_rag_scores([])
