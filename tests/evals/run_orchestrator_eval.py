"""Offline evaluation for the learning agent orchestrator.

Agents are replaced with scripted stand-ins so the run exercises orchestration
alone: which agent is chosen, in what order, what context reaches the next one,
and what survives when a step cannot run. No model and no database are involved,
so the suite is free and reproduces bit for bit.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from app.agents.integrity import IntegrityDecision, IntegrityLevel
from app.agents.learning_agents import ClarifyAgent, IntegrityGuardAgent
from app.agents.orchestrator import LearningAgentOrchestrator
from app.agents.protocol import (
    AgentResult,
    AgentStatus,
    AgentTask,
    LearningContext,
    ToolCall,
)
from app.agents.routing import (
    AgentName,
    ExecutionMode,
    LearningIntent,
    QueryPlan,
    RouteTarget,
    RoutingDecision,
    RoutingSource,
    decision_for,
)
from app.core.exceptions import AppError
from app.schemas.tutor import TutorScope
from tests.evals.orchestrator_metrics import (
    aggregate_orchestrator_scores,
    score_orchestrator_case,
)


DATASET_VERSION = "orchestrator-v1"
COURSE_ID = UUID("00000000-0000-0000-0000-0000000000c1")
USER_ID = UUID("00000000-0000-0000-0000-0000000000a1")


class ScriptedAgent:
    """Stands in for a real agent, recording what it was asked to do."""

    def __init__(self, name: AgentName, script: dict[str, Any]) -> None:
        self.name = name
        self.script = script
        self.tasks: list[AgentTask] = []

    async def run(self, task: AgentTask, context: LearningContext) -> AgentResult:
        self.tasks.append(task)
        if self.script.get("raises") == "RuntimeError":
            raise RuntimeError("scripted failure")
        if self.script.get("raises") == "AppError":
            raise AppError("SCRIPTED_FAILURE", "scripted failure")
        return AgentResult(
            answer=f"[{self.name.value} answer]",
            status=AgentStatus(self.script.get("status", "ok")),
            evidence_status=self.script.get("evidence_status", "sufficient"),
            model_name=f"{self.name.value}-model",
            fallback_reason=self.script.get("fallback_reason"),
            tool_calls=[
                ToolCall(item, ok=True, latency_ms=0)
                for item in self.script.get("tool_calls", [])
            ],
            shared=self.script.get("shared", {}),
        )


def _plan() -> QueryPlan:
    return QueryPlan(
        standalone_query="q",
        course_id=COURSE_ID,
        document_types=[],
        document_ids=[],
        page_from=None,
        page_to=None,
        requested_language="zh",
        top_k=8,
    )


def _decision(case: dict[str, Any]) -> RoutingDecision:
    supporting = [AgentName(item) for item in case.get("supporting", [])]
    decision = decision_for(
        LearningIntent(case["intent"]),
        confidence=0.9,
        reason="eval",
        query_plan=_plan(),
        supporting_agents=supporting,
    )
    if case.get("source") == "llm":
        from dataclasses import replace

        decision = replace(decision, source=RoutingSource.LLM)
    if case.get("target") == "clarify":
        from dataclasses import replace

        decision = replace(
            decision,
            target=RouteTarget.CLARIFY,
            execution_mode=ExecutionMode.CLARIFY,
            clarification="clarify-me",
        )
    return decision


def _integrity(case: dict[str, Any]) -> IntegrityDecision | None:
    level = case.get("integrity")
    if level is None:
        return None
    return IntegrityDecision(
        IntegrityLevel(level), reason="eval", notice="notice" if level != "learning_allowed" else ""
    )


async def _run_case(case: dict[str, Any]) -> dict[str, Any]:
    unregistered = set(case.get("unregistered", []))
    agents = {
        AgentName(name): ScriptedAgent(AgentName(name), script)
        for name, script in case["agents"].items()
        if name not in unregistered
    }
    orchestrator = LearningAgentOrchestrator(
        registry=dict(agents),
        clarify_agent=ClarifyAgent(),
        integrity_agent=IntegrityGuardAgent(),
    )
    decision = _decision(case)
    context = LearningContext(
        user_id=USER_ID,
        course_id=COURSE_ID,
        conversation_id=uuid4(),
        message="eval message",
        language="zh",
        mode="standard",
        scope=TutorScope(),
        decision=decision,
        integrity=_integrity(case),
    )

    result, trace = await orchestrator.run(context)
    payload = trace.as_dict()
    steps = payload["steps"]
    # A primary, clarify or guard step always ran; only a supporting step can be
    # skipped or fail. Status alone is not the test: the integrity guard reports
    # SKIPPED to mean "no course agent ran", yet it produced the answer itself.
    ran = [
        step
        for step in steps
        if step["role"] != "supporting" or step["status"] not in {"skipped", "failed"}
    ]
    primary_step = ran[0] if ran else None
    supporting_agent = next(
        (agent for name, agent in agents.items() if name in decision.supporting_agents),
        None,
    )

    return {
        "sequence": [step["agent"] for step in ran],
        "invoked": [name.value for name, agent in agents.items() if agent.tasks],
        "primary": primary_step["agent"] if primary_step else None,
        "mode": decision.execution_mode.value,
        "merged": "\n\n---\n\n" in (result.answer or ""),
        "supporting_input": (
            supporting_agent.tasks[0].inputs if supporting_agent and supporting_agent.tasks else None
        ),
        "step_status": {step["agent"]: step["status"] for step in steps},
        "roles": [step["role"] for step in ran],
        "tool_calls": [call["name"] for step in steps for call in step["tool_calls"]],
        "answer": result.answer,
        "primary_answer": f"[{primary_step['agent']} answer]" if primary_step else None,
        "status": result.status.value,
        "fallback_reason": result.fallback_reason,
        "trace_id": payload["trace_id"],
        "trace_integrity": payload["route"].get("integrity"),
    }


async def _run(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scores = []
    for case in cases:
        score = score_orchestrator_case(case, await _run_case(case))
        scores.append(score)
        flag = "ok  " if score["passed"] else "FAIL"
        print(f"{flag} {score['id']:<20} {score['observed_sequence']}")
        if not score["passed"]:
            print(f"     failed checks: {', '.join(score['failed_checks'])}")
    return scores


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    metrics = report["metrics"]
    lines = [
        f"# StudyPilot Orchestrator Eval — {report['dataset_version']}",
        "",
        f"- Cases: {metrics['case_count']}",
        f"- Generated: {report['generated_at']}",
        "",
        "| Metric | Result |",
        "|---|---:|",
    ]
    for key, value in metrics.items():
        if key == "by_category":
            continue
        lines.append(
            f"| {key} | {value * 100:.2f}% |" if isinstance(value, float) else f"| {key} | {value} |"
        )
    lines += ["", "## By category", "", "| Category | Cases | Pass rate |", "|---|---:|---:|"]
    for name, stats in metrics["by_category"].items():
        lines.append(f"| {name} | {stats['case_count']} | {stats['pass_rate'] * 100:.2f}% |")

    failures = [item for item in report["cases"] if not item["passed"]]
    if failures:
        lines += ["", "## Failed cases", ""]
        for item in failures:
            lines.append(
                f"- `{item['id']}` failed {', '.join(item['failed_checks'])}; "
                f"expected `{item['expected_sequence']}`, got `{item['observed_sequence']}`"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the StudyPilot orchestrator evaluation.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--category", default=None)
    args = parser.parse_args()

    dataset = Path(__file__).parent / "datasets" / "orchestrator_flows_v1.jsonl"
    cases = [
        json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines() if line
    ]
    if args.category:
        cases = [case for case in cases if case["category"] == args.category]
    if args.limit:
        cases = cases[: args.limit]

    scores = asyncio.run(_run(cases))
    metrics = aggregate_orchestrator_scores(scores)
    report = {
        "dataset_version": DATASET_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "cases": scores,
    }
    output = Path("artifacts/evals")
    output.mkdir(parents=True, exist_ok=True)
    (output / "orchestrator_latest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_markdown(output / "orchestrator_latest.md", report)

    print()
    for key, value in metrics.items():
        if key != "by_category":
            print(f"{key}: {value}")
    print("\nWrote artifacts/evals/orchestrator_latest.json and orchestrator_latest.md")


if __name__ == "__main__":
    main()
