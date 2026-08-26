"""Scoring for the hybrid learning intent router evaluation."""

from __future__ import annotations

from typing import Any


def score_router_case(case: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    """Score one routed case against its expected structured decision."""

    expected_intent = case["expected_intent"]
    expected_supporting = sorted(case.get("expected_supporting", []))
    actual_supporting = sorted(decision.get("supporting_agents", []))
    expects_clarification = bool(case.get("expect_clarification", False))
    clarified = decision.get("target") == "clarify"

    plan = decision.get("query_plan", {})
    scope = case.get("scope", {})
    scope_preserved = (
        plan.get("document_ids", []) == scope.get("document_ids", [])
        and plan.get("document_types", []) == scope.get("document_types", [])
        and plan.get("page_from") == scope.get("page_from")
        and plan.get("page_to") == scope.get("page_to")
    )

    return {
        "id": case["id"],
        "category": case["category"],
        "expected_intent": expected_intent,
        "actual_intent": decision.get("intent"),
        "intent_correct": decision.get("intent") == expected_intent,
        "supporting_correct": actual_supporting == expected_supporting,
        "expected_supporting": expected_supporting,
        "actual_supporting": actual_supporting,
        "execution_mode": decision.get("execution_mode"),
        "execution_mode_correct": (
            decision.get("execution_mode") == ("sequential" if expected_supporting else "single")
            or clarified
        ),
        "source": decision.get("source"),
        "resolved_by_rule": decision.get("source") == "rule",
        "confidence": decision.get("confidence"),
        "scope_preserved": scope_preserved,
        "expects_clarification": expects_clarification,
        "clarified": clarified,
        "clarification_correct": clarified == expects_clarification,
        "latency_ms": decision.get("latency_ms"),
    }


def aggregate_router_scores(scores: list[dict[str, Any]]) -> dict[str, Any]:
    if not scores:
        return {"case_count": 0}

    total = len(scores)
    # Clarification is a valid outcome, so intent accuracy is measured only where
    # the router was expected to commit to an intent.
    decisive = [item for item in scores if not item["expects_clarification"]]
    composite = [item for item in scores if item["expected_supporting"]]
    latencies = [item["latency_ms"] for item in scores if item["latency_ms"] is not None]

    return {
        "case_count": total,
        "decisive_case_count": len(decisive),
        "composite_case_count": len(composite),
        "intent_accuracy": _ratio(decisive, "intent_correct"),
        "execution_mode_accuracy": _ratio(scores, "execution_mode_correct"),
        "composite_supporting_accuracy": _ratio(composite, "supporting_correct"),
        "clarification_accuracy": _ratio(scores, "clarification_correct"),
        "scope_preservation_rate": _ratio(scores, "scope_preserved"),
        "rule_resolution_rate": _ratio(scores, "resolved_by_rule"),
        "llm_invocation_rate": 1.0 - _ratio(scores, "resolved_by_rule"),
        "average_latency_ms": (sum(latencies) / len(latencies)) if latencies else 0.0,
        "by_category": _by_category(scores),
    }


def _ratio(items: list[dict[str, Any]], key: str) -> float:
    if not items:
        return 1.0
    return sum(1 for item in items if item[key]) / len(items)


def _by_category(scores: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    categories: dict[str, list[dict[str, Any]]] = {}
    for item in scores:
        categories.setdefault(item["category"], []).append(item)
    return {
        name: {
            "case_count": len(items),
            "intent_accuracy": _ratio(
                [entry for entry in items if not entry["expects_clarification"]],
                "intent_correct",
            ),
            "rule_resolution_rate": _ratio(items, "resolved_by_rule"),
        }
        for name, items in sorted(categories.items())
    }
