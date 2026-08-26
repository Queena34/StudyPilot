"""Score a completed human faithfulness review.

Takes the verdicts a reviewer exported from the review page and turns them into
the same shape as the other suites, so a human judgement can sit alongside the
automatic ones and be compared across runs.

A half-finished sheet is refused rather than scored, because a partial review
that reports 100% is worse than no review at all.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from tests.evals.faithfulness_metrics import (
    aggregate_faithfulness_scores,
    score_faithfulness_case,
    validate_verdicts,
)


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    metrics = report["metrics"]
    lines = [
        f"# StudyPilot Faithfulness Review — {report['dataset_version']}",
        "",
        f"- Reviewed: {metrics['case_count']} answers "
        f"({metrics['answerable_case_count']} answerable, {metrics['unanswerable_case_count']} out-of-material)",
        f"- Sampled: {report['sampled_at']}",
        f"- Scored: {report['scored_at']}",
        f"- Reviewer: {report['reviewer']}",
        "",
        "| Metric | Result |",
        "|---|---:|",
    ]
    for key, value in metrics.items():
        if key == "by_stratum":
            continue
        lines.append(
            f"| {key} | {value * 100:.2f}% |" if isinstance(value, float) else f"| {key} | {value} |"
        )
    lines += ["", "## By stratum", "", "| Stratum | Cases | Grounded | Fabrication |", "|---|---:|---:|---:|"]
    for name, stats in metrics["by_stratum"].items():
        lines.append(
            f"| {name} | {stats['case_count']} | {stats['grounding_rate'] * 100:.2f}% | "
            f"{stats['fabrication_rate'] * 100:.2f}% |"
        )

    flagged = [
        item for item in report["cases"]
        if item["fabricated"] or item["any_grounding_problem"] or item["citations_wrong"]
        or item["answered_anyway"]
    ]
    if flagged:
        lines += ["", "## Flagged answers", ""]
        for item in flagged:
            reasons = [
                label for label, hit in (
                    ("编造内容", item["fabricated"]),
                    ("依据不足", item["any_grounding_problem"]),
                    ("引用指错", item["citations_wrong"]),
                    ("资料外问题却作答", item["answered_anyway"]),
                ) if hit
            ]
            lines.append(f"- `{item['id']}` [{item['stratum']}] {'、'.join(reasons)}")
            if item["note"]:
                lines.append(f"  - 评审备注：{item['note']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Score a completed faithfulness review.")
    parser.add_argument("--verdicts", type=Path, required=True, help="Exported verdicts JSON.")
    parser.add_argument(
        "--sample",
        type=Path,
        default=Path("artifacts/evals/faithfulness_sample.json"),
    )
    parser.add_argument("--reviewer", default="unnamed", help="Who reviewed the sample.")
    args = parser.parse_args()

    sample = json.loads(args.sample.read_text(encoding="utf-8"))
    verdicts = json.loads(args.verdicts.read_text(encoding="utf-8"))
    cases = sample["cases"]

    problems = validate_verdicts(cases, verdicts)
    if problems:
        print("评审尚未完成，未进行评分：")
        for problem in problems[:20]:
            print(f"  - {problem}")
        if len(problems) > 20:
            print(f"  … 另有 {len(problems) - 20} 项")
        raise SystemExit(1)

    scores = [score_faithfulness_case(case, verdicts[case["id"]]) for case in cases]
    metrics = aggregate_faithfulness_scores(scores)
    report = {
        "dataset_version": sample["dataset_version"],
        "sampled_at": sample["sampled_at"],
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "reviewer": args.reviewer,
        "seed": sample["seed"],
        "metrics": metrics,
        "cases": scores,
    }
    output = Path("artifacts/evals")
    output.mkdir(parents=True, exist_ok=True)
    (output / "faithfulness_latest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_markdown(output / "faithfulness_latest.md", report)

    for key, value in metrics.items():
        if key != "by_stratum":
            print(f"{key}: {value}")
    print("\nWrote artifacts/evals/faithfulness_latest.json and faithfulness_latest.md")


if __name__ == "__main__":
    main()
