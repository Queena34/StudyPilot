from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from time import monotonic
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tests.evals.metrics import aggregate_rag_scores, score_rag_case


DATASET_VERSION = "rag-v1"


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
    except (HTTPError, URLError) as exc:
        raise RuntimeError(f"Eval request failed for {url}: {exc}") from exc


def _load_cases(path: Path) -> list[dict[str, Any]]:
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("dataset contains duplicate case IDs")
    return cases


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    metrics = report["metrics"]
    lines = [
        f"# StudyPilot RAG Eval — {report['dataset_version']}",
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
    lines.extend(["", "## Failed cases", ""])
    required_checks = (
        "citation_validity",
        "document_scope_adherence",
        "section_scope_adherence",
        "no_answer_correct",
    )
    failed = [
        item
        for item in report["results"]
        if not all(item[key] for key in required_checks)
    ]
    lines.extend([f"- `{item['id']}`" for item in failed] or ["None"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run StudyPilot RAG evaluation against a local API")
    parser.add_argument("--course-id", required=True)
    parser.add_argument("--base-url", default="http://localhost:8000/api/v1")
    parser.add_argument("--dataset", type=Path, default=Path("tests/evals/datasets/rag_questions_v1.jsonl"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/evals"))
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    cases = _load_cases(args.dataset)
    if args.limit:
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
        response = _json_request(
            f"{args.base_url}/courses/{args.course_id}/tutor/messages",
            method="POST",
            body={
                "message": case["question"],
                "response_language": "zh",
                "mode": "deep",
                "scope": {"document_ids": [document_ids[case["document"]]]},
            },
        )
        latency_ms = round((monotonic() - started) * 1000)
        results.append(score_rag_case(case, response, latency_ms))
        raw_responses.append({"id": case["id"], "response": response})

    model_names = sorted({item["model_name"] for item in results if item["model_name"]})
    report = {
        "dataset_version": DATASET_VERSION,
        "dataset_path": str(args.dataset),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_name": ", ".join(model_names) or "unknown",
        "metrics": aggregate_rag_scores(results),
        "results": results,
        "raw_responses": raw_responses,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "rag_latest.json"
    md_path = args.output_dir / "rag_latest.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_markdown(md_path, report)
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    print(f"Wrote {json_path} and {md_path}")


if __name__ == "__main__":
    main()
