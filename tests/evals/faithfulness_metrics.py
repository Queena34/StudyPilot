"""Scoring for the human faithfulness spot-check.

Every other suite measures proxies a machine can decide: does a citation parse,
does it point inside the requested document, does a keyword appear. None of them
can answer the question the product actually rests on — is this answer true to
the material it cites. That judgement is human, so this module scores verdicts a
person recorded rather than anything computed from the answer text.
"""

from __future__ import annotations

from typing import Any

#: What a reviewer may record for each sampled answer.
GROUNDING_VERDICTS = ("supported", "partially_supported", "unsupported")
CITATION_VERDICTS = ("accurate", "imprecise", "wrong")

REQUIRED_FIELDS = ("grounding", "citations", "fabricated", "admits_gap")


def score_faithfulness_case(case: dict[str, Any], verdict: dict[str, Any]) -> dict[str, Any]:
    grounding = verdict.get("grounding")
    citations = verdict.get("citations")
    fabricated = bool(verdict.get("fabricated"))
    admits_gap = verdict.get("admits_gap")

    return {
        "id": case["id"],
        "stratum": case.get("stratum", "unknown"),
        "answerable": case.get("answerable", True),
        "grounding": grounding,
        "citations": citations,
        "fabricated": fabricated,
        "admits_gap": admits_gap,
        "fully_grounded": grounding == "supported",
        "any_grounding_problem": grounding in {"partially_supported", "unsupported"},
        "citations_accurate": citations == "accurate",
        "citations_wrong": citations == "wrong",
        # An unanswerable question is only handled correctly if the answer says so.
        "correctly_declined": (not case.get("answerable", True)) and bool(admits_gap),
        "answered_anyway": (not case.get("answerable", True)) and not admits_gap,
        "note": verdict.get("note", ""),
    }


def aggregate_faithfulness_scores(scores: list[dict[str, Any]]) -> dict[str, Any]:
    if not scores:
        return {"case_count": 0}

    answerable = [item for item in scores if item["answerable"]]
    unanswerable = [item for item in scores if not item["answerable"]]

    return {
        "case_count": len(scores),
        "answerable_case_count": len(answerable),
        "unanswerable_case_count": len(unanswerable),
        "grounding_rate": _ratio(answerable, "fully_grounded"),
        "grounding_problem_rate": _ratio(answerable, "any_grounding_problem"),
        "citation_accuracy_rate": _ratio(answerable, "citations_accurate"),
        "citation_wrong_rate": _ratio(answerable, "citations_wrong"),
        # The most serious failure: a claim the sources do not contain.
        "fabrication_rate": _ratio(scores, "fabricated"),
        "declined_when_unsupported_rate": _ratio(unanswerable, "correctly_declined"),
        "answered_unsupported_rate": _ratio(unanswerable, "answered_anyway"),
        "by_stratum": _by_stratum(scores),
    }


def _ratio(items: list[dict[str, Any]], key: str) -> float:
    if not items:
        return 0.0 if key.endswith(("problem_rate", "wrong_rate", "fabrication_rate")) else 1.0
    return sum(1 for item in items if item[key]) / len(items)


def _by_stratum(scores: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    strata: dict[str, list[dict[str, Any]]] = {}
    for item in scores:
        strata.setdefault(item["stratum"], []).append(item)
    return {
        name: {
            "case_count": len(items),
            "grounding_rate": _ratio(items, "fully_grounded"),
            "fabrication_rate": _ratio(items, "fabricated"),
        }
        for name, items in sorted(strata.items())
    }


def validate_verdicts(
    cases: list[dict[str, Any]], verdicts: dict[str, dict[str, Any]]
) -> list[str]:
    """Refuse to score a half-filled sheet, so a partial review cannot be
    mistaken for a clean result."""

    problems: list[str] = []
    for case in cases:
        verdict = verdicts.get(case["id"])
        if verdict is None:
            problems.append(f"{case['id']}: 未评审")
            continue
        for field in REQUIRED_FIELDS:
            if verdict.get(field) is None:
                problems.append(f"{case['id']}: 缺少 {field}")
        if verdict.get("grounding") not in GROUNDING_VERDICTS + (None,):
            problems.append(f"{case['id']}: grounding 取值非法 {verdict.get('grounding')!r}")
        if verdict.get("citations") not in CITATION_VERDICTS + (None,):
            problems.append(f"{case['id']}: citations 取值非法 {verdict.get('citations')!r}")
    return problems
