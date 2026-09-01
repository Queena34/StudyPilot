"""Offline evaluation for paraphrase robustness of the intent router.

Runs the router in-process, like the routing eval. Each group holds several ways
of asking for the same thing; the number that matters is whether the router gave
them all the same answer.
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
from app.core.config import get_settings
from app.schemas.tutor import TutorScope
from tests.evals.paraphrase_metrics import (
    aggregate_paraphrase_scores,
    score_paraphrase_case,
)

DATASET_VERSION = "router-paraphrase-v1"
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


async def _run(cases: list[dict[str, Any]], *, rules_only: bool) -> list[dict[str, Any]]:
    router = LearningIntentRouter(llm_router=_DisabledLLMRouter() if rules_only else None)
    scores = []
    for case in cases:
        started = monotonic()
        decision = await router.route(
            message=case["message"],
            standalone_query=case["message"],
            course_id=COURSE_ID,
            language="zh",
            scope=TutorScope(),
        )
        payload = decision.as_dict()
        payload["latency_ms"] = round((monotonic() - started) * 1000)
        scores.append(score_paraphrase_case(case, payload))
    return scores


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    metrics = report["metrics"]
    lines = [
        f"# StudyPilot Paraphrase Eval — {report['dataset_version']}",
        "",
        f"- Mode: `{report['mode']}`",
        f"- Model: `{report['model']}`",
        f"- Groups: {metrics['group_count']} / Cases: {metrics['case_count']}",
        f"- Generated: {report['generated_at']}",
        "",
        "| Metric | Result |",
        "|---|---:|",
    ]
    for key, value in metrics.items():
        if key == "by_group":
            continue
        if isinstance(value, float) and key.endswith(("accuracy", "rate", "consistency")):
            lines.append(f"| {key} | {value * 100:.2f}% |")
        elif isinstance(value, float):
            lines.append(f"| {key} | {value:.2f} |")
        else:
            lines.append(f"| {key} | {value} |")

    lines += ["", "## By group", "", "| Group | Cases | Consistent | All correct | Intents seen |", "|---|---:|---|---|---|"]
    for name, stats in metrics["by_group"].items():
        lines.append(
            f"| {name} | {stats['case_count']} | {'yes' if stats['consistent'] else 'NO'} | "
            f"{'yes' if stats['all_correct'] else 'no'} | {', '.join(stats['intents_seen'])} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rules-only", action="store_true")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("tests/evals/datasets/router_paraphrase_v1.jsonl"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/evals"))
    args = parser.parse_args()

    cases = _load_cases(args.dataset)
    scores = asyncio.run(_run(cases, rules_only=args.rules_only))
    metrics = aggregate_paraphrase_scores(scores)

    report = {
        "dataset_version": DATASET_VERSION,
        "mode": "rules_only" if args.rules_only else "hybrid",
        "model": "rules-only" if args.rules_only else get_settings().anthropic_model,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "cases": scores,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "paraphrase_latest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_markdown(args.output_dir / "paraphrase_latest.md", report)

    for key, value in metrics.items():
        if key != "by_group":
            print(f"{key}: {value}")
    print("\nWrote artifacts/evals/paraphrase_latest.json and paraphrase_latest.md")


if __name__ == "__main__":
    main()
