"""Scoring for the orchestrator evaluation.

Roadmap section 9 asks the orchestrator to be evaluated on four things: which
agent it picks, in what order it runs them, whether context reaches the next
agent, and how it degrades when a step cannot run. Those are scored separately,
because a layer that picks the right agents but loses the answer on a failing
follow-up is not partially correct — it is broken in the way that matters.
"""

from __future__ import annotations

from typing import Any


def score_orchestrator_case(case: dict[str, Any], observed: dict[str, Any]) -> dict[str, Any]:
    expect = case["expect"]
    checks: dict[str, bool] = {}

    checks["agent_sequence"] = observed["sequence"] == expect["sequence"]
    if "primary" in expect:
        checks["primary_agent"] = observed["primary"] == expect["primary"]
    for agent in expect.get("not_invoked", []):
        checks[f"not_invoked:{agent}"] = agent not in observed["invoked"]
    if "mode" in expect:
        checks["execution_mode"] = observed["mode"] == expect["mode"]
    if "supporting_input" in expect:
        checks["context_passing"] = _matches(
            observed.get("supporting_input") or {}, expect["supporting_input"]
        )
    if "merged" in expect:
        checks["output_merged"] = observed["merged"] is expect["merged"]
    for agent in expect.get("skipped", []):
        checks[f"skipped:{agent}"] = observed["step_status"].get(agent) == "skipped"
    for agent in expect.get("failed", []):
        checks[f"failed:{agent}"] = observed["step_status"].get(agent) == "failed"
    if expect.get("primary_answer_preserved"):
        checks["primary_answer_preserved"] = observed["answer"] == observed["primary_answer"]
    if "result_status" in expect:
        checks["result_status"] = observed["status"] == expect["result_status"]
    if "fallback_reason" in expect:
        checks["fallback_reason"] = observed["fallback_reason"] == expect["fallback_reason"]
    if "answer_contains" in expect:
        checks["answer_contains"] = expect["answer_contains"] in (observed["answer"] or "")
    if "tool_calls" in expect:
        checks["tool_calls_recorded"] = observed["tool_calls"] == expect["tool_calls"]
    if "roles" in expect:
        checks["step_roles"] = observed["roles"] == expect["roles"]
    if expect.get("has_trace_id"):
        checks["trace_id"] = bool(observed.get("trace_id"))
    if expect.get("trace_has_integrity"):
        checks["trace_integrity"] = observed.get("trace_integrity") is not None

    return {
        "id": case["id"],
        "category": case["category"],
        "checks": checks,
        "passed": all(checks.values()),
        "failed_checks": [name for name, ok in checks.items() if not ok],
        "observed_sequence": observed["sequence"],
        "expected_sequence": expect["sequence"],
    }


def _matches(observed: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(observed.get(key) == value for key, value in expected.items())


def aggregate_orchestrator_scores(scores: list[dict[str, Any]]) -> dict[str, Any]:
    if not scores:
        return {"case_count": 0}

    def rate(prefix: str) -> float:
        relevant = [
            ok
            for item in scores
            for name, ok in item["checks"].items()
            if name.startswith(prefix)
        ]
        return sum(relevant) / len(relevant) if relevant else 1.0

    return {
        "case_count": len(scores),
        "case_pass_rate": sum(1 for item in scores if item["passed"]) / len(scores),
        "agent_selection_accuracy": rate("primary_agent"),
        "execution_order_accuracy": rate("agent_sequence"),
        "isolation_rate": rate("not_invoked:"),
        "execution_mode_accuracy": rate("execution_mode"),
        "context_passing_accuracy": rate("context_passing"),
        # The degradation guarantee: a failing follow-up must not lose the answer.
        "answer_preservation_rate": rate("primary_answer_preserved"),
        "skip_correctness": rate("skipped:"),
        "failure_containment": rate("failed:"),
        "trace_completeness": (rate("tool_calls_recorded") + rate("step_roles") + rate("trace_id")) / 3,
        "by_category": _by_category(scores),
    }


def _by_category(scores: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    categories: dict[str, list[dict[str, Any]]] = {}
    for item in scores:
        categories.setdefault(item["category"], []).append(item)
    return {
        name: {
            "case_count": len(items),
            "pass_rate": sum(1 for entry in items if entry["passed"]) / len(items),
        }
        for name, items in sorted(categories.items())
    }
