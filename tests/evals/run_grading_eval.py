from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from time import monotonic
from typing import Any

from app.llm.evaluation_gateway import AnswerEvaluationGateway
from app.services.attempt_service import _score_evaluation
from tests.evals.grading_metrics import aggregate_grading_scores, score_grading_run


DATASET_VERSION = "grading-v1"


def _load_cases(path: Path) -> list[dict[str, Any]]:
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("dataset contains duplicate case IDs")
    return cases


async def _run(args) -> dict[str, Any]:
    cases = _load_cases(args.dataset)
    if args.limit:
        cases = cases[: args.limit]
    gateway = AnswerEvaluationGateway()
    results = []
    raw_outputs = []
    for case in cases:
        for level in ("correct", "partial", "incorrect"):
            for repeat in range(1, args.repeats + 1):
                started = monotonic()
                evaluation_dict = None
                model_name = None
                score = None
                error = None
                try:
                    evaluation, model_name = await gateway.evaluate(
                        question=case["question"],
                        answer=case["answers"][level],
                        reference_answer=case["reference_answer"],
                        rubric=case["rubric"],
                        sources=case["sources"],
                        include_language_feedback=False,
                    )
                    _, score = _score_evaluation(
                        evaluation, case["rubric"], case["sources"]
                    )
                    evaluation_dict = evaluation.model_dump(mode="json")
                except Exception as exc:  # Keep the full eval running and report the failure.
                    error = f"{type(exc).__name__}: {exc}"
                latency_ms = round((monotonic() - started) * 1000)
                result = score_grading_run(
                    case=case,
                    level=level,
                    repeat=repeat,
                    score=score,
                    evaluation=evaluation_dict,
                    model_name=model_name,
                    latency_ms=latency_ms,
                    error=error,
                )
                results.append(result)
                raw_outputs.append(
                    {"id": result["id"], "evaluation": evaluation_dict, "error": error}
                )
    model_names = sorted({item["model_name"] for item in results if item["model_name"]})
    return {
        "dataset_version": DATASET_VERSION,
        "dataset_path": str(args.dataset),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_name": ", ".join(model_names) or "unknown",
        "repeats": args.repeats,
        "metrics": aggregate_grading_scores(results),
        "results": results,
        "raw_outputs": raw_outputs,
    }


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        f"# StudyPilot Grading Eval — {report['dataset_version']}",
        "",
        f"- Model: `{report['model_name']}`",
        f"- Repeats per answer: {report['repeats']}",
        f"- Generated: {report['generated_at']}",
        "",
        "| Metric | Result |",
        "|---|---:|",
    ]
    for key, value in report["metrics"].items():
        rendered = "N/A" if value is None else str(value)
        if isinstance(value, float) and key not in {
            "average_latency_ms",
            "average_correct_score",
            "average_partial_score",
            "average_incorrect_score",
        }:
            rendered = f"{value:.2%}"
        lines.append(f"| {key} | {rendered} |")
    failed = [item for item in report["results"] if not item["run_success"]]
    lines.extend(["", "## Failed runs", ""])
    lines.extend([f"- `{item['id']}`: {item['error']}" for item in failed] or ["None"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run StudyPilot grading evaluation")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("tests/evals/datasets/grading_answers_v1.jsonl"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/evals"))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.repeats < 1:
        raise ValueError("repeats must be at least 1")

    report = asyncio.run(_run(args))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "grading_latest.json"
    md_path = args.output_dir / "grading_latest.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_markdown(md_path, report)
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    print(f"Wrote {json_path} and {md_path}")


if __name__ == "__main__":
    main()
