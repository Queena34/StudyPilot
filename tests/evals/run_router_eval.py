"""Offline evaluation for the hybrid learning intent router.

Unlike the RAG, quiz and grading runners, this one calls the router in-process:
routing has no retrieval or database dependency, so the eval stays fast and needs
no running API. `--rules-only` disables the LLM stage for a deterministic,
zero-cost run; the full run consults the configured model for unclear messages.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import UUID

from app.agents.intent_router import LearningIntentRouter
from app.schemas.tutor import TutorScope
from tests.evals.router_metrics import aggregate_router_scores, score_router_case


DATASET_VERSION = "router-v1"
COURSE_ID = UUID("00000000-0000-0000-0000-0000000000ff")


class _DisabledLLMRouter:
    async def propose(self, *, message, history=None):  # noqa: ARG002 - fixed signature
        return None


def _load_cases(path: Path) -> list[dict[str, Any]]:
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("dataset contains duplicate case IDs")
    return cases


def _scope_of(case: dict[str, Any]) -> TutorScope:
    scope = case.get("scope", {})
    return TutorScope(
        document_types=scope.get("document_types", []),
        document_ids=[UUID(value) for value in scope.get("document_ids", [])],
        page_from=scope.get("page_from"),
        page_to=scope.get("page_to"),
    )


async def _run_case(
    router: LearningIntentRouter, case: dict[str, Any]
) -> dict[str, Any]:
    history = [(role, content) for role, content in case.get("history", [])]
    started = monotonic()
    decision = await router.route(
        message=case["message"],
        standalone_query=case["message"],
        course_id=COURSE_ID,
        language="zh",
        scope=_scope_of(case),
        history=history,
    )
    payload = decision.as_dict()
    payload["latency_ms"] = round((monotonic() - started) * 1000)
    return payload


async def _run(cases: list[dict[str, Any]], *, rules_only: bool) -> list[dict[str, Any]]:
    router = LearningIntentRouter(llm_router=_DisabledLLMRouter() if rules_only else None)
    scores = []
    for case in cases:
        decision = await _run_case(router, case)
        score = score_router_case(case, decision)
        score["message"] = case["message"]
        score["reason"] = decision.get("reason")
        scores.append(score)
        flag = "ok " if score["intent_correct"] or score["expects_clarification"] else "MISS"
        print(f"{flag} {score['id']:<16} {score['actual_intent']:<22} {score['source']}")
    return scores


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    metrics = report["metrics"]
    lines = [
        f"# StudyPilot Router Eval — {report['dataset_version']}",
        "",
        f"- Mode: `{report['mode']}`",
        f"- Model: `{report['model']}`",
        f"- Cases: {metrics['case_count']}",
        f"- Generated: {report['generated_at']}",
        "",
        "| Metric | Result |",
        "|---|---:|",
    ]
    for key, value in metrics.items():
        if key in {"by_category"}:
            continue
        if isinstance(value, float) and key.endswith(("accuracy", "rate")):
            lines.append(f"| {key} | {value * 100:.2f}% |")
        elif isinstance(value, float):
            lines.append(f"| {key} | {value:.2f} |")
        else:
            lines.append(f"| {key} | {value} |")

    lines += ["", "## By category", "", "| Category | Cases | Intent accuracy | Rule resolution |", "|---|---:|---:|---:|"]
    for name, stats in metrics["by_category"].items():
        lines.append(
            f"| {name} | {stats['case_count']} | "
            f"{stats['intent_accuracy'] * 100:.2f}% | {stats['rule_resolution_rate'] * 100:.2f}% |"
        )

    misses = [
        item
        for item in report["cases"]
        if not item["expects_clarification"] and not item["intent_correct"]
    ]
    if misses:
        lines += ["", "## Misrouted cases", ""]
        for item in misses:
            lines.append(
                f"- `{item['id']}` {item['message']} → expected `{item['expected_intent']}`, "
                f"got `{item['actual_intent']}` (source `{item['source']}`)"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the StudyPilot router evaluation.")
    parser.add_argument("--limit", type=int, default=None, help="Run only the first N cases.")
    parser.add_argument(
        "--rules-only",
        action="store_true",
        help="Disable the LLM stage; deterministic and free.",
    )
    parser.add_argument("--category", default=None, help="Run one category only.")
    args = parser.parse_args()

    dataset = Path(__file__).parent / "datasets" / "router_intents_v1.jsonl"
    cases = _load_cases(dataset)
    if args.category:
        cases = [case for case in cases if case["category"] == args.category]
    if args.limit:
        cases = cases[: args.limit]

    scores = asyncio.run(_run(cases, rules_only=args.rules_only))
    metrics = aggregate_router_scores(scores)

    model = "rules-only"
    if not args.rules_only:
        from app.core.config import get_settings

        settings = get_settings()
        model = settings.anthropic_model if settings.anthropic_api_key else "not-configured"

    report = {
        "dataset_version": DATASET_VERSION,
        "mode": "rules-only" if args.rules_only else "hybrid",
        "model": model,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "cases": scores,
    }

    output = Path("artifacts/evals")
    output.mkdir(parents=True, exist_ok=True)
    (output / "router_latest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_markdown(output / "router_latest.md", report)

    print()
    for key, value in metrics.items():
        if key == "by_category":
            continue
        print(f"{key}: {value}")
    print("\nWrote artifacts/evals/router_latest.json and router_latest.md")


if __name__ == "__main__":
    main()
