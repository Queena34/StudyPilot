"""Scoring for paraphrase robustness of the intent router.

The routing set asks whether one phrasing is understood. This one asks whether
*the same request* is understood the same way however it is worded, which the
routing set could not see: two composite-detection designs scored identically on
all 57 of its cases, and only phrasings outside its vocabulary separated them.

So the headline number here is not accuracy but **group consistency** — every
message in a group asks for the same thing, so the router giving them different
answers is a defect even when some of those answers are right. A learner who
rephrases and gets a different behaviour has found a bug, not a preference.
"""

from __future__ import annotations

from typing import Any

from app.agents.routing import INTENT_AGENTS, LearningIntent


def score_paraphrase_case(case: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    # Order is the whole point: the orchestrator runs supporting agents in list
    # order, so [planner, progress] plans the revision before reading which
    # topics are weak. Sorting both sides hid that — the metric claimed to check
    # the supporting agents while being blind to the one thing that makes the
    # workflow executable.
    expected_supporting = list(case.get("expected_supporting", []))
    actual_supporting = list(decision.get("supporting_agents", []))
    return {
        "id": case["id"],
        "group": case["group"],
        "message": case["message"],
        "expected_intent": case["expected_intent"],
        "actual_intent": decision.get("intent"),
        "intent_correct": decision.get("intent") == case["expected_intent"],
        # Same lesson as the routing set: two labels can reach one agent, and a
        # learner feels the agent, not the label.
        "actual_agent": decision.get("primary_agent"),
        "agent_correct": decision.get("primary_agent")
        == INTENT_AGENTS[LearningIntent(case["expected_intent"])].value,
        "expected_supporting": expected_supporting,
        "actual_supporting": actual_supporting,
        "supporting_correct": actual_supporting == expected_supporting,
        "clarified": decision.get("target") == "clarify",
        "resolved_by_rule": decision.get("source") == "rule",
        "latency_ms": decision.get("latency_ms"),
    }


def aggregate_paraphrase_scores(scores: list[dict[str, Any]]) -> dict[str, Any]:
    if not scores:
        return {"case_count": 0}

    groups: dict[str, list[dict[str, Any]]] = {}
    for item in scores:
        groups.setdefault(item["group"], []).append(item)

    consistent = 0
    agent_consistent = 0
    fully_correct = 0
    composite_groups = 0
    composite_consistent = 0
    details: dict[str, Any] = {}
    for name, items in sorted(groups.items()):
        intents = {item["actual_intent"] for item in items}
        agents = {item["actual_agent"] for item in items}
        supporting = {tuple(item["actual_supporting"]) for item in items}
        is_consistent = len(intents) == 1 and len(supporting) == 1
        agent_is_consistent = len(agents) == 1 and len(supporting) == 1
        agent_consistent += agent_is_consistent
        is_correct = all(item["intent_correct"] and item["supporting_correct"] for item in items)
        consistent += is_consistent
        fully_correct += is_correct
        if items[0]["expected_supporting"]:
            composite_groups += 1
            composite_consistent += is_consistent
        details[name] = {
            "case_count": len(items),
            "consistent": is_consistent,
            "agent_consistent": agent_is_consistent,
            "all_correct": is_correct,
            # The distinct readings the router gave one request, so a failure
            # names the phrasings that diverged instead of only counting them.
            "intents_seen": sorted(intents),
            "supporting_seen": sorted(list(item) for item in supporting),
        }

    latencies = [item["latency_ms"] for item in scores if item["latency_ms"] is not None]
    return {
        "case_count": len(scores),
        "group_count": len(groups),
        "composite_group_count": composite_groups,
        # Every phrasing in a group means the same thing; disagreeing is a defect.
        "group_consistency": consistent / len(groups),
        "agent_group_consistency": agent_consistent / len(groups),
        "composite_group_consistency": (
            composite_consistent / composite_groups if composite_groups else 1.0
        ),
        "group_full_accuracy": fully_correct / len(groups),
        "intent_accuracy": _ratio(scores, "intent_correct"),
        "agent_accuracy": _ratio(scores, "agent_correct"),
        "supporting_accuracy": _ratio(scores, "supporting_correct"),
        "clarification_rate": _ratio(scores, "clarified"),
        "rule_resolution_rate": _ratio(scores, "resolved_by_rule"),
        "average_latency_ms": (sum(latencies) / len(latencies)) if latencies else 0.0,
        "by_group": details,
    }


def _ratio(items: list[dict[str, Any]], key: str) -> float:
    if not items:
        return 1.0
    return sum(1 for item in items if item[key]) / len(items)
