from __future__ import annotations

from statistics import mean
from typing import Any


NO_ANSWER_MARKERS = (
    "没有找到足够证据",
    "资料中没有",
    "没有给出",
    "没有介绍",
    "没有教授",
    "没有涉及",
    "未涉及",
    "不包含",
    "完全没有",
    "无法从",
    "insufficient evidence",
    "not found in the",
    "does not contain",
    "not included",
)

# Dataset terms represent concepts, not exact answer wording. Each concept can be
# expressed in either course language without being counted twice.
TERM_ALIASES: dict[str, tuple[str, ...]] = {
    "anova": ("anova", "方差分析"),
    "between": ("between", "组间"),
    "breakdown": ("breakdown", "故障", "击穿"),
    "conditional": ("conditional", "条件"),
    "equal": ("equal", "相等", "相同"),
    "error": ("error", "error term", "误差", "误差项"),
    "expectation": ("expectation", "期望", "期望值"),
    "extrapolation": ("extrapolation", "外推"),
    "fisher": ("fisher", "费希尔"),
    "fitted": ("fitted", "拟合值", "预测值"),
    "geyser": ("geyser", "间歇泉"),
    "independent": ("independent", "independence", "独立", "独立性"),
    "intercept": ("intercept", "截距"),
    "least squares": ("least squares", "最小二乘"),
    "linear": ("linear", "线性"),
    "log": ("log", "logarithm", "对数"),
    "mean": ("mean", "平均", "均值", "期望"),
    "multiple": ("multiple", "多重比较", "多重检验"),
    "normal": ("normal", "normality", "正态", "正态性"),
    "null": ("null", "原假设", "零假设"),
    "observed": ("observed", "观测值", "实际值"),
    "p-value": ("p-value", "p value", "p值", "p 值"),
    "phobic": ("phobic", "恐惧"),
    "random": ("random", "randomization", "随机", "随机化"),
    "residual": ("residual", "残差"),
    "response": ("response", "响应"),
    "slope": ("slope", "斜率"),
    "total": ("total", "总变异", "总离差"),
    "variance": ("variance", "变异", "方差"),
    "within": ("within", "组内"),
}


def _concept_aliases(term: Any) -> tuple[str, ...]:
    """Return normalized aliases for a dataset concept or custom alias list."""
    if isinstance(term, list):
        aliases = term
    else:
        key = str(term).casefold()
        aliases = TERM_ALIASES.get(key, (str(term),))
    return tuple(str(alias).casefold() for alias in aliases if str(alias).strip())


def score_rag_case(case: dict[str, Any], response: dict[str, Any], latency_ms: int) -> dict[str, Any]:
    answer = str(response.get("answer") or "")
    citations = response.get("citations") or []
    answerable = bool(case["answerable"])
    expected_concepts = [_concept_aliases(term) for term in case.get("expected_terms", [])]
    # Strip markdown emphasis before matching: the model writes "**没有**教授",
    # and the asterisks would split a marker phrase that is plainly present.
    normalized_answer = answer.casefold().replace("*", "").replace("_", "")
    matched_terms = [
        next(alias for alias in aliases if alias in normalized_answer)
        for aliases in expected_concepts
        if any(alias in normalized_answer for alias in aliases)
    ]
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
    section_scored = answerable and bool(expected_section)
    section_scope_adherence = (
        any(expected_section in str(citation.get("section_title") or "").casefold() for citation in citations)
        if section_scored
        else True
    )
    refusal = response.get("evidence_status") == "insufficient" or any(
        marker in normalized_answer for marker in NO_ANSWER_MARKERS
    )
    no_answer_scored = not answerable
    no_answer_correct = refusal if no_answer_scored else True
    return {
        "id": case["id"],
        "answerable": answerable,
        "latency_ms": latency_ms,
        "citation_validity": citation_validity,
        "document_scope_adherence": document_scope_adherence,
        "section_scope_adherence": section_scope_adherence,
        "section_scored": section_scored,
        "no_answer_correct": no_answer_correct,
        "no_answer_scored": no_answer_scored,
        "keyword_coverage": len(matched_terms) / max(1, len(expected_concepts)),
        "matched_terms": matched_terms,
        "citation_count": len(citations),
        "fallback": bool(response.get("fallback_reason")),
        "model_name": (response.get("usage") or {}).get("model_name"),
    }


def aggregate_rag_scores(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        raise ValueError("results cannot be empty")

    def rate(field: str, items: list[dict[str, Any]] = results) -> float:
        return mean(1.0 if item[field] else 0.0 for item in items) if items else 0.0

    answerable = [item for item in results if item["answerable"]]
    section_scored = [item for item in results if item.get("section_scored")]
    no_answer_scored = [item for item in results if item.get("no_answer_scored")]
    return {
        "case_count": len(results),
        "answerable_count": len(answerable),
        "section_scored_count": len(section_scored),
        "no_answer_count": len(no_answer_scored),
        "citation_validity": rate("citation_validity"),
        "document_scope_adherence": rate("document_scope_adherence"),
        "section_scope_adherence": rate("section_scope_adherence", section_scored),
        "no_answer_accuracy": rate("no_answer_correct", no_answer_scored),
        "keyword_coverage": mean(item["keyword_coverage"] for item in answerable) if answerable else 0.0,
        "fallback_rate": mean(1.0 if item["fallback"] else 0.0 for item in results),
        "average_latency_ms": round(mean(item["latency_ms"] for item in results), 2),
    }
