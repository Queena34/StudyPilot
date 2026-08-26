from __future__ import annotations

from statistics import mean
from typing import Any


NO_ANSWER_MARKERS = (
    "没有找到足够证据",
    "资料中没有",
    "无法从",
    "insufficient evidence",
    "not found in the",
)


def score_rag_case(case: dict[str, Any], response: dict[str, Any], latency_ms: int) -> dict[str, Any]:
    answer = str(response.get("answer") or "")
    citations = response.get("citations") or []
    answerable = bool(case["answerable"])
    expected_terms = [term.casefold() for term in case.get("expected_terms", [])]
    normalized_answer = answer.casefold()
    matched_terms = [term for term in expected_terms if term in normalized_answer]
    citations_well_formed = all(
        citation.get("document_id")
        and citation.get("filename")
        and isinstance(citation.get("page_number"), int)
        and citation.get("page_number", 0) >= 1
        and citation.get("chunk_id")
        for citation in citations
    )
    citation_validity = citations_well_formed and (bool(citations) or not answerable)
    expected_document = case.get("document")
    document_scope_adherence = (
        all(citation.get("filename") == expected_document for citation in citations)
        if citations and expected_document
        else not answerable
    )
    expected_section = (case.get("section_contains") or "").casefold()
    section_scope_adherence = (
        any(expected_section in str(citation.get("section_title") or "").casefold() for citation in citations)
        if answerable and expected_section
        else True
    )
    refusal = response.get("evidence_status") == "insufficient" or any(
        marker in normalized_answer for marker in NO_ANSWER_MARKERS
    )
    no_answer_correct = refusal if not answerable else not refusal
    return {
        "id": case["id"],
        "answerable": answerable,
        "latency_ms": latency_ms,
        "citation_validity": citation_validity,
        "document_scope_adherence": document_scope_adherence,
        "section_scope_adherence": section_scope_adherence,
        "no_answer_correct": no_answer_correct,
        "keyword_coverage": len(matched_terms) / max(1, len(expected_terms)),
        "matched_terms": matched_terms,
        "citation_count": len(citations),
        "fallback": bool(response.get("fallback_reason")),
        "model_name": (response.get("usage") or {}).get("model_name"),
    }


def aggregate_rag_scores(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        raise ValueError("results cannot be empty")

    def rate(field: str) -> float:
        return mean(1.0 if item[field] else 0.0 for item in results)

    answerable = [item for item in results if item["answerable"]]
    return {
        "case_count": len(results),
        "answerable_count": len(answerable),
        "citation_validity": rate("citation_validity"),
        "document_scope_adherence": rate("document_scope_adherence"),
        "section_scope_adherence": rate("section_scope_adherence"),
        "no_answer_accuracy": rate("no_answer_correct"),
        "keyword_coverage": mean(item["keyword_coverage"] for item in answerable) if answerable else 0.0,
        "fallback_rate": mean(1.0 if item["fallback"] else 0.0 for item in results),
        "average_latency_ms": round(mean(item["latency_ms"] for item in results), 2),
    }
