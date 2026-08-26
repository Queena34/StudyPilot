"""Offline evaluation for the academic integrity guard.

The guard is fully deterministic and calls no model, so this run is free, fast
and bit-for-bit reproducible. That is the point: a rule deciding what help a
student receives should be verifiable the same way every time.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from app.agents.integrity import AcademicIntegrityGuard, IntegrityLevel
from tests.evals.integrity_metrics import (
    aggregate_integrity_scores,
    score_integrity_case,
)


DATASET_VERSION = "integrity-v1"


def _load_cases(path: Path) -> list[dict[str, Any]]:
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("dataset contains duplicate case IDs")
    return cases


def _evaluate(guard: AcademicIntegrityGuard, case: dict[str, Any]) -> dict[str, Any]:
    decision = guard.evaluate(case["message"], language=case.get("language", "zh"))
    return {
        "level": decision.level.value,
        "reason": decision.reason,
        "notice": decision.notice,
        # A turn still delivers help unless the guard blocked the answer outright.
        "has_help": decision.level is not IntegrityLevel.LIVE_EXAM_PROHIBITED,
        "answer_constraint": decision.answer_constraint,
    }


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    metrics = report["metrics"]
    lines = [
        f"# StudyPilot Integrity Eval — {report['dataset_version']}",
        "",
        f"- Cases: {metrics['case_count']} "
        f"({metrics['legitimate_case_count']} legitimate, {metrics['restricted_case_count']} restricted)",
        f"- Generated: {report['generated_at']}",
        "",
        "| Metric | Result |",
        "|---|---:|",
    ]
    for key, value in metrics.items():
        if key == "by_category":
            continue
        if isinstance(value, float):
            lines.append(f"| {key} | {value * 100:.2f}% |")
        else:
            lines.append(f"| {key} | {value} |")

    lines += [
        "",
        "## By category",
        "",
        "| Category | Cases | Level accuracy | False positive rate |",
        "|---|---:|---:|---:|",
    ]
    for name, stats in metrics["by_category"].items():
        lines.append(
            f"| {name} | {stats['case_count']} | {stats['level_accuracy'] * 100:.2f}% | "
            f"{stats['false_positive_rate'] * 100:.2f}% |"
        )

    misses = [item for item in report["cases"] if not item["correct"]]
    if misses:
        lines += ["", "## Misclassified cases", ""]
        for item in misses:
            kind = (
                "FALSE POSITIVE"
                if item["false_positive"]
                else "false negative"
                if item["false_negative"]
                else "wrong severity"
            )
            lines.append(
                f"- `{item['id']}` [{kind}] {item['message']} → expected "
                f"`{item['expected_level']}`, got `{item['actual_level']}`"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the StudyPilot integrity guard evaluation.")
    parser.add_argument("--limit", type=int, default=None, help="Run only the first N cases.")
    parser.add_argument("--category", default=None, help="Run one category only.")
    args = parser.parse_args()

    dataset = Path(__file__).parent / "datasets" / "integrity_requests_v1.jsonl"
    cases = _load_cases(dataset)
    if args.category:
        cases = [case for case in cases if case["category"] == args.category]
    if args.limit:
        cases = cases[: args.limit]

    guard = AcademicIntegrityGuard()
    scores = []
    for case in cases:
        score = score_integrity_case(case, _evaluate(guard, case))
        scores.append(score)
        if score["false_positive"]:
            flag = "FALSE-POS"
        elif not score["correct"]:
            flag = "MISS     "
        else:
            flag = "ok       "
        print(f"{flag} {score['id']:<18} {score['actual_level']}")

    metrics = aggregate_integrity_scores(scores)
    report = {
        "dataset_version": DATASET_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "cases": scores,
    }

    output = Path("artifacts/evals")
    output.mkdir(parents=True, exist_ok=True)
    (output / "integrity_latest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_markdown(output / "integrity_latest.md", report)

    print()
    for key, value in metrics.items():
        if key != "by_category":
            print(f"{key}: {value}")
    print("\nWrote artifacts/evals/integrity_latest.json and integrity_latest.md")


if __name__ == "__main__":
    main()
