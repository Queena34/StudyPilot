from __future__ import annotations

from statistics import mean
from typing import Any

from tests.evals.metrics import _concept_aliases


def score_quiz_case(
    case: dict[str, Any],
    response: dict[str, Any] | None,
    latency_ms: int,
    error_code: str | None = None,
) -> dict[str, Any]:
    expected_rejection = bool(case.get("expected_rejection"))
    rejected = response is None
    generation_success = (
        rejected and error_code == "INSUFFICIENT_EVIDENCE"
        if expected_rejection
        else not rejected
    )
    questions = (response or {}).get("questions") or []
    expected_count = int(case["question_count"])
    expected_type = case["question_type"]
    expected_difficulty = case["difficulty"]
    expected_document = case["document"]
    page_from = case.get("page_from")
    page_to = case.get("page_to")

    sources = [source for question in questions for source in (question.get("sources") or [])]
    citation_validity = bool(sources) and all(
        source.get("document_id")
        and source.get("filename")
        and isinstance(source.get("page_number"), int)
        and source.get("page_number", 0) >= 1
        and source.get("chunk_id")
        for source in sources
    )
    document_scope_adherence = bool(sources) and all(
        source.get("filename") == expected_document for source in sources
    )
    page_scope_adherence = (
        bool(sources)
        and all(
            (page_from is None or source["page_number"] >= page_from)
            and (page_to is None or source["page_number"] <= page_to)
            for source in sources
        )
        if page_from is not None or page_to is not None
        else True
    )
    options_format_valid = bool(questions) and all(
        _valid_options(question, expected_type) for question in questions
    )
    question_completeness = bool(questions) and all(
        str(question.get("content") or "").strip()
        and question.get("knowledge_points")
        and question.get("sources")
        for question in questions
    )
    topic_text = " ".join(
        " ".join(
            [
                str(question.get("content") or ""),
                " ".join(str(value) for value in question.get("knowledge_points") or []),
                " ".join(
                    str(option.get("text") or "")
                    for option in question.get("options") or []
                ),
            ]
        )
        for question in questions
    ).casefold()
    concepts = [_concept_aliases(term) for term in case.get("expected_terms", [])]
    topic_matches = [
        next(alias for alias in aliases if alias in topic_text)
        for aliases in concepts
        if any(alias in topic_text for alias in aliases)
    ]
    topic_coverage = len(topic_matches) / max(1, len(concepts))

    return {
        "id": case["id"],
        "expected_rejection": expected_rejection,
        "rejected": rejected,
        "error_code": error_code,
        "generation_success": generation_success,
        "question_count_adherence": len(questions) == expected_count if not rejected else False,
        "question_type_adherence": (
            bool(questions)
            and all(question.get("question_type") == expected_type for question in questions)
        ),
        "difficulty_adherence": (
            bool(questions)
            and all(question.get("difficulty") == expected_difficulty for question in questions)
        ),
        "options_format_valid": options_format_valid,
        "question_completeness": question_completeness,
        "citation_validity": citation_validity,
        "document_scope_adherence": document_scope_adherence,
        "page_scope_adherence": page_scope_adherence,
        "page_scope_scored": page_from is not None or page_to is not None,
        "topic_coverage": topic_coverage,
        "topic_matches": topic_matches,
        "question_count": len(questions),
        "fallback": (response or {}).get("model_name") == "quiz-fallback",
        "model_name": (response or {}).get("model_name"),
        "latency_ms": latency_ms,
    }


def _valid_options(question: dict[str, Any], expected_type: str) -> bool:
    options = question.get("options")
    if expected_type != "single_choice":
        return options in (None, [])
    if not isinstance(options, list) or len(options) != 4:
        return False
    ids = [str(option.get("id") or "").strip() for option in options]
    texts = [str(option.get("text") or "").strip() for option in options]
    return all(ids) and all(texts) and len(set(ids)) == 4


def aggregate_quiz_scores(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        raise ValueError("results cannot be empty")

    generated = [item for item in results if not item["expected_rejection"] and not item["rejected"]]
    rejection_cases = [item for item in results if item["expected_rejection"]]
    page_scored = [item for item in generated if item["page_scope_scored"]]

    def rate(field: str, items: list[dict[str, Any]]) -> float:
        return mean(1.0 if item[field] else 0.0 for item in items) if items else 0.0

    return {
        "case_count": len(results),
        "generated_case_count": len(generated),
        "rejection_case_count": len(rejection_cases),
        "generation_success_rate": rate("generation_success", results),
        "rejection_accuracy": (
            rate("generation_success", rejection_cases) if rejection_cases else None
        ),
        "question_count_adherence": (
            rate("question_count_adherence", generated) if generated else None
        ),
        "question_type_adherence": (
            rate("question_type_adherence", generated) if generated else None
        ),
        "difficulty_adherence": rate("difficulty_adherence", generated) if generated else None,
        "options_format_validity": (
            rate("options_format_valid", generated) if generated else None
        ),
        "question_completeness": (
            rate("question_completeness", generated) if generated else None
        ),
        "citation_validity": rate("citation_validity", generated) if generated else None,
        "document_scope_adherence": (
            rate("document_scope_adherence", generated) if generated else None
        ),
        "page_scope_adherence": (
            rate("page_scope_adherence", page_scored) if page_scored else None
        ),
        "topic_coverage": (
            mean(item["topic_coverage"] for item in generated) if generated else None
        ),
        "fallback_rate": rate("fallback", generated) if generated else None,
        "average_latency_ms": round(mean(item["latency_ms"] for item in results), 2),
    }
