from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from time import monotonic
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tests.evals.quiz_metrics import aggregate_quiz_scores, score_quiz_case


DATASET_VERSION = "quiz-v1"


def _json_request(url: str, *, method: str = "GET", body: dict | None = None) -> dict[str, Any]:
    payload = json.dumps(body).encode() if body is not None else None
    request = Request(
        url,
        data=payload,
        method=method,
        headers={"Content-Type": "application/json"} if payload else {},
    )
    try:
        with urlopen(request, timeout=180) as response:  # noqa: S310 - explicit local eval URL
            return json.loads(response.read())
    except HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body_text)
        except json.JSONDecodeError:
            detail = {"detail": body_text}
        error = RuntimeError(f"HTTP {exc.code}: {detail}")
        error.code = _error_code(detail)  # type: ignore[attr-defined]
        raise error from exc
    except URLError as exc:
        raise RuntimeError(f"Eval request failed for {url}: {exc}") from exc


def _error_code(payload: dict[str, Any]) -> str | None:
    error = payload.get("error")
    if isinstance(error, dict):
        return error.get("code")
    detail = payload.get("detail")
    if isinstance(detail, dict):
        return detail.get("code")
    return payload.get("code")


def _load_cases(path: Path) -> list[dict[str, Any]]:
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("dataset contains duplicate case IDs")
    return cases


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    metrics = report["metrics"]
    lines = [
        f"# StudyPilot Quiz Eval — {report['dataset_version']}",
        "",
        f"- Model: `{report['model_name']}`",
        f"- Cases: {metrics['case_count']}",
        f"- Generated: {report['generated_at']}",
        "",
        "| Metric | Result |",
        "|---|---:|",
    ]
    for key, value in metrics.items():
        rendered = (
            f"{value:.2%}"
            if isinstance(value, float) and key != "average_latency_ms"
            else str(value)
        )
        lines.append(f"| {key} | {rendered} |")
    failures = [item["id"] for item in report["results"] if not item["generation_success"]]
    lines.extend(["", "## Failed generation/rejection cases", ""])
    lines.extend([f"- `{item}`" for item in failures] or ["None"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run StudyPilot quiz generation evaluation")
    parser.add_argument("--course-id", required=True)
    parser.add_argument("--base-url", default="http://localhost:8000/api/v1")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("tests/evals/datasets/quiz_generation_v1.jsonl"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/evals"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--smoke", action="store_true", help="Run the three tagged smoke cases")
    args = parser.parse_args()

    cases = _load_cases(args.dataset)
    if args.smoke:
        cases = [case for case in cases if "smoke" in case.get("tags", [])]
        if len(cases) != 3:
            raise ValueError("quiz smoke suite must contain exactly three tagged cases")
    elif args.limit:
        cases = cases[: args.limit]
    documents = _json_request(f"{args.base_url}/courses/{args.course_id}/documents?size=100")["items"]
    document_ids = {item["filename"]: item["id"] for item in documents if item["status"] == "ready"}
    missing = sorted({case["document"] for case in cases} - set(document_ids))
    if missing:
        raise RuntimeError(f"Required ready documents are missing: {', '.join(missing)}")

    results = []
    raw_responses = []
    for case in cases:
        started = monotonic()
        response = None
        error_code = None
        error_message = None
        try:
            response = _json_request(
                f"{args.base_url}/courses/{args.course_id}/practice-sets",
                method="POST",
                body={
                    "title": f"[EVAL:{DATASET_VERSION}:{case['id']}]",
                    "topic": case["topic"],
                    "question_type": case["question_type"],
                    "difficulty": case["difficulty"],
                    "question_count": case["question_count"],
                    "language": "zh",
                    "scope": {
                        "document_ids": [document_ids[case["document"]]],
                        "page_from": case.get("page_from"),
                        "page_to": case.get("page_to"),
                    },
                },
            )
        except RuntimeError as exc:
            error_code = getattr(exc, "code", None)
            error_message = str(exc)
        latency_ms = round((monotonic() - started) * 1000)
        results.append(score_quiz_case(case, response, latency_ms, error_code))
        raw_responses.append(
            {"id": case["id"], "response": response, "error": error_message}
        )

    model_names = sorted({item["model_name"] for item in results if item["model_name"]})
    report = {
        "dataset_version": DATASET_VERSION,
        "dataset_path": str(args.dataset),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_name": ", ".join(model_names) or "unknown",
        "metrics": aggregate_quiz_scores(results),
        "results": results,
        "raw_responses": raw_responses,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "quiz_latest.json"
    md_path = args.output_dir / "quiz_latest.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_markdown(md_path, report)
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    print(f"Wrote {json_path} and {md_path}")


if __name__ == "__main__":
    main()
