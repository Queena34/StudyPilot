"""Scoring for cross-language retrieval.

The suite exists because of a failure the other seven missed. Retrieval was
returning arbitrary passages for Chinese questions about English material, and
the answers still looked right — the model wrote from prior knowledge and hung
citations on passages that merely shared a word. Every existing metric passed.

The difference here is where the expected terms are looked for: in the **cited
passages**, not in the answer. An answer can be correct without being grounded;
a citation cannot be correct without carrying what it is cited for.
"""

from __future__ import annotations

from typing import Any


def score_retrieval_case(
    case: dict[str, Any], language: str, response: dict[str, Any], latency_ms: int
) -> dict[str, Any]:
    citations = response.get("citations") or []
    plan = response.get("query_plan") or {}
    passages = " ".join(str(item.get("snippet") or "") for item in citations).lower()
    answer = str(response.get("answer") or "").lower()
    terms = [term.lower() for term in case.get("terms", [])]
    answerable = bool(case["answerable"])

    # Grounded means the passages carry the subject, not just the answer text.
    supported = any(term in passages for term in terms) if terms else None
    claimed = any(term in answer for term in terms) if terms else None

    return {
        "id": case["id"],
        "language": language,
        "question": case[language],
        "answerable": answerable,
        "citation_count": len(citations),
        "evidence_status": response.get("evidence_status"),
        "translated": bool(
            plan.get("retrieval_query")
            and plan.get("retrieval_query") != plan.get("standalone_query")
        ),
        "retrieval_query": plan.get("retrieval_query"),
        "has_citations": bool(citations) if answerable else True,
        "citations_support_subject": bool(supported) if answerable and terms else True,
        # The dangerous combination: the answer asserts the subject while no
        # cited passage contains it.
        "ungrounded_claim": bool(answerable and terms and claimed and not supported),
        "declined_when_unsupported": (not answerable)
        and response.get("evidence_status") in {"insufficient", "partial"},
        "latency_ms": latency_ms,
    }


def aggregate_retrieval_scores(scores: list[dict[str, Any]]) -> dict[str, Any]:
    if not scores:
        return {"case_count": 0}

    answerable = [item for item in scores if item["answerable"]]
    zh = [item for item in answerable if item["language"] == "zh"]
    en = [item for item in answerable if item["language"] == "en"]

    return {
        "case_count": len(scores),
        "answerable_case_count": len(answerable),
        "citation_support_rate": _ratio(answerable, "citations_support_subject"),
        "citation_support_rate_zh": _ratio(zh, "citations_support_subject"),
        "citation_support_rate_en": _ratio(en, "citations_support_subject"),
        # Parity is the point: a Chinese question must retrieve as well as the
        # same question in the material's own language.
        "cross_language_parity": (
            _ratio(zh, "citations_support_subject") / _ratio(en, "citations_support_subject")
            if en and _ratio(en, "citations_support_subject")
            else 0.0
        ),
        "ungrounded_claim_rate": _ratio(answerable, "ungrounded_claim"),
        "has_citations_rate": _ratio(answerable, "has_citations"),
        "translation_rate_zh": _ratio(zh, "translated"),
        "average_latency_ms": sum(item["latency_ms"] for item in scores) / len(scores),
    }


def _ratio(items: list[dict[str, Any]], key: str) -> float:
    if not items:
        return 0.0 if key.startswith("ungrounded") else 1.0
    return sum(1 for item in items if item[key]) / len(items)
