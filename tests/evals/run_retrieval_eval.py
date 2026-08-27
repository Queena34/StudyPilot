"""Cross-language retrieval evaluation.

Asks each question twice — in the learner's language and in the material's — and
compares what the citations actually contain. Deliberately runs **unscoped**: no
document is pinned, which is the path where retrieval failed unnoticed.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from time import monotonic
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tests.evals.retrieval_metrics import aggregate_retrieval_scores, score_retrieval_case

DATASET_VERSION = "retrieval-crosslingual-v1"


def _post(url: str, body: dict) -> dict[str, Any]:
    request = Request(
        url, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=180) as response:  # noqa: S310 - local eval URL
            return json.loads(response.read())
    except HTTPError as error:
        return {"answer": "", "citations": [], "evidence_status": f"http_{error.code}"}
    except URLError as error:
        raise RuntimeError(f"request failed: {error}") from error


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    metrics = report["metrics"]
    lines = [
        f"# StudyPilot Cross-language Retrieval — {report['dataset_version']}",
        "", f"- Cases: {metrics['case_count']} (asked in both languages)",
        f"- Generated: {report['generated_at']}", "",
        "| Metric | Result |", "|---|---:|",
    ]
    for key, value in metrics.items():
        if isinstance(value, float) and key.endswith(("rate", "parity", "rate_zh", "rate_en")):
            lines.append(f"| {key} | {value * 100:.2f}% |")
        elif isinstance(value, float):
            lines.append(f"| {key} | {value:.0f} |")
        else:
            lines.append(f"| {key} | {value} |")
    bad = [item for item in report["cases"] if not item["citations_support_subject"]]
    if bad:
        lines += ["", "## Citations that do not carry the subject", ""]
        for item in bad:
            lines.append(
                f"- `{item['id']}` [{item['language']}] {item['question']}"
                + ("  ← 答案声称了主题但引用中没有" if item["ungrounded_claim"] else "")
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the cross-language retrieval eval.")
    parser.add_argument("--course-id", required=True)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    dataset = Path(__file__).parent / "datasets" / "retrieval_crosslingual_v1.jsonl"
    cases = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines() if line]
    if args.limit:
        cases = cases[: args.limit]

    url = f"{args.base_url.rstrip('/')}/api/v1/courses/{args.course_id}/tutor/messages"
    scores = []
    for case in cases:
        for language in ("zh", "en"):
            started = monotonic()
            payload = _post(url, {"message": case[language], "response_language": "zh"})
            score = score_retrieval_case(
                case, language, payload, round((monotonic() - started) * 1000)
            )
            scores.append(score)
            flag = "ok  " if score["citations_support_subject"] else "MISS"
            if score["ungrounded_claim"]:
                flag = "UNGROUNDED"
            print(f"{flag:<11} {score['id']}[{language}] {score['citation_count']} 引用")

    metrics = aggregate_retrieval_scores(scores)
    report = {
        "dataset_version": DATASET_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "course_id": args.course_id,
        "metrics": metrics,
        "cases": scores,
    }
    output = Path("artifacts/evals")
    output.mkdir(parents=True, exist_ok=True)
    (output / "retrieval_latest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_markdown(output / "retrieval_latest.md", report)
    print()
    for key, value in metrics.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
