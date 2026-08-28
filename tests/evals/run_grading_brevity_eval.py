"""Diagnostic: does the grader penalise brevity?

Grading v1 lost 10% of its score-band accuracy to three partial answers that
each covered one of two rubric criteria and were scored as if they covered
neither. Stripping their self-commentary fixed one; the other two stayed low,
which suggested the grader marks down criteria the answer states plainly but
tersely. Three samples is not enough to act on, so this measures the tendency
before anything is changed.

Each case isolates **one** rubric criterion, reweighted to 1.0, so the earned
ratio is read directly rather than inferred from a total. The same criterion is
answered four ways:

    brief_correct    states it in as few words as possible
    verbose_correct  the same content, elaborated — the control for length
    hedged_correct   correct but unconfident wording
    near_miss        related and plausible, but does not state it — the control
                     against concluding "just grade more generously"

A gap between brief and verbose is the tendency. A near_miss scoring well would
mean the grader is already too generous, and loosening it would be wrong.

This does not modify grading-v1 or its baseline.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean

from app.llm.evaluation_gateway import AnswerEvaluationGateway

DATASET_VERSION = "grading-brevity-v1"


async def _grade(gateway: AnswerEvaluationGateway, case: dict, repeats: int) -> list[float]:
    ratios = []
    for _ in range(repeats):
        evaluation, _model = await gateway.evaluate(
            question=case["question"],
            answer=case["answer"],
            reference_answer=case["reference_answer"],
            rubric=case["rubric"],
            sources=case["sources"],
            include_language_feedback=False,
        )
        results = evaluation.criterion_results
        ratios.append(float(results[0].earned_ratio) if results else 0.0)
    return ratios


async def main_async(args) -> None:
    dataset = Path(__file__).parent / "datasets" / "grading_brevity_v1.jsonl"
    cases = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines() if line]
    if args.limit:
        cases = cases[: args.limit]

    gateway = AnswerEvaluationGateway()
    rows = []
    for case in cases:
        ratios = await _grade(gateway, case, args.repeats)
        average = mean(ratios)
        rows.append({**{k: case[k] for k in ("id", "source_question", "style", "answer",
                                             "expected_ratio")},
                     "criterion": case["rubric"][0]["criterion"],
                     "ratios": ratios, "mean_ratio": round(average, 3),
                     "matches_expectation": abs(average - case["expected_ratio"]) <= 0.25})
        flag = "ok  " if rows[-1]["matches_expectation"] else "OFF "
        print(f"{flag} {case['id']:<12} {case['style']:<16} ratio={average:.2f} "
              f"(期望 {case['expected_ratio']:.1f})")

    by_style = defaultdict(list)
    for row in rows:
        by_style[row["style"]].append(row["mean_ratio"])
    summary = {style: round(mean(values), 3) for style, values in sorted(by_style.items())}
    brief, verbose = summary.get("brief_correct", 0), summary.get("verbose_correct", 0)

    metrics = {
        "case_count": len(rows),
        "repeats": args.repeats,
        "mean_ratio_by_style": summary,
        # The number this diagnostic exists to produce.
        "brevity_penalty": round(verbose - brief, 3),
        "hedging_penalty": round(verbose - summary.get("hedged_correct", 0), 3),
        "near_miss_leakage": summary.get("near_miss", 0),
        "expectation_match_rate": round(
            sum(1 for row in rows if row["matches_expectation"]) / len(rows), 3),
    }
    report = {"dataset_version": DATASET_VERSION,
              "generated_at": datetime.now(timezone.utc).isoformat(),
              "metrics": metrics, "cases": rows}
    output = Path("artifacts/evals")
    output.mkdir(parents=True, exist_ok=True)
    (output / "grading_brevity_latest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n每种表述的平均得分比例：")
    for style, value in summary.items():
        print(f"  {style:<16} {value:.3f}")
    print(f"\n简短惩罚 (verbose − brief): {metrics['brevity_penalty']:+.3f}")
    print(f"含糊惩罚 (verbose − hedged): {metrics['hedging_penalty']:+.3f}")
    print(f"近似答案得分 (应接近 0)   : {metrics['near_miss_leakage']:.3f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose grader brevity bias.")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--limit", type=int)
    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
