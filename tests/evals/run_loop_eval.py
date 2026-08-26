"""End-to-end evaluation of the closed learning loop (roadmap section 9, item 3).

Drives the real API through the sequence a learner actually follows — explain,
generate practice, submit an answer, have mastery updated, receive a plan — and
checks the postcondition of each stage against live state rather than against a
mock. This is the only suite that can answer whether the loop still closes after
a model, prompt or routing change.

It needs a running StudyPilot with a course that already has processed material,
and it does create real practice sets, attempts and study plans for that course.
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


DATASET_VERSION = "loop-v1"
MARKER = "[EVAL:loop-v1]"


def _request(url: str, *, method: str = "GET", body: dict | None = None) -> dict[str, Any]:
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
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code}: {detail}") from error
    except URLError as error:
        raise RuntimeError(f"request failed for {url}: {error}") from error


class LoopRunner:
    def __init__(self, base_url: str, course_id: str) -> None:
        self.base = base_url.rstrip("/")
        self.course_id = course_id
        self.conversation_id: str | None = None
        self.stages: list[dict[str, Any]] = []

    def _chat(self, message: str, **extra) -> dict[str, Any]:
        body = {"message": message, **extra}
        if self.conversation_id:
            body["conversation_id"] = self.conversation_id
        started = monotonic()
        payload = _request(
            f"{self.base}/api/v1/courses/{self.course_id}/tutor/messages",
            method="POST",
            body=body,
        )
        payload["_latency_ms"] = round((monotonic() - started) * 1000)
        self.conversation_id = payload["conversation_id"]
        return payload

    def _record(self, name: str, checks: dict[str, bool], detail: dict[str, Any]) -> None:
        self.stages.append(
            {
                "stage": name,
                "checks": checks,
                "passed": all(checks.values()),
                "failed_checks": [key for key, ok in checks.items() if not ok],
                "detail": detail,
            }
        )
        flag = "ok  " if all(checks.values()) else "FAIL"
        print(f"{flag} {name:<22} {detail.get('summary', '')}")
        if not all(checks.values()):
            print(f"     failed: {', '.join(key for key, ok in checks.items() if not ok)}")

    def stage_explain(self, topic: str) -> None:
        answer = self._chat(f"请讲解一下{topic}")
        citations = answer.get("citations", [])
        trace = answer.get("trace", {})
        self._record(
            "1-explain",
            {
                "routed_to_tutor": trace.get("agent_sequence", [])[:1] == ["tutor"],
                "has_citations": bool(citations),
                "citations_resolve": all(item.get("filename") for item in citations),
                "evidence_sufficient": answer.get("evidence_status") in {"sufficient", "partial"},
                "integrity_allowed": answer.get("integrity", {}).get("level") == "learning_allowed",
            },
            {
                "summary": f"{len(citations)} citation(s), {answer['_latency_ms']}ms",
                "latency_ms": answer["_latency_ms"],
                "evidence_status": answer.get("evidence_status"),
            },
        )

    def stage_practice(self) -> dict[str, Any]:
        answer = self._chat(
            "给我出2道简答题",
            practice_options={"question_type": "short_answer", "difficulty": "medium", "question_count": 2},
        )
        practice = answer.get("practice_set") or {}
        questions = practice.get("questions") or []
        self._record(
            "2-practice",
            {
                "practice_created": bool(questions),
                "requested_count_honoured": len(questions) == 2,
                "questions_have_sources": all(item.get("sources") for item in questions),
                "routed_to_quiz": "quiz" in answer.get("trace", {}).get("agent_sequence", []),
            },
            {
                "summary": f"{len(questions)} question(s), {answer['_latency_ms']}ms",
                "latency_ms": answer["_latency_ms"],
                "practice_set_id": practice.get("id"),
            },
        )
        return practice

    def stage_grade(self) -> dict[str, Any]:
        answer = self._chat("我的答案是：这个概念大概就是把数据处理一下，我不太确定")
        trace = answer.get("trace", {})
        graded = answer.get("evidence_status") == "graded"
        self._record(
            "3-grade",
            {
                "routed_to_evaluator": "evaluator" in trace.get("agent_sequence", []),
                "graded": graded,
                "score_reported": "得分" in (answer.get("answer") or "")
                or "Score" in (answer.get("answer") or ""),
                "grade_tool_called": any(
                    call["name"] == "grade_answer"
                    for step in trace.get("steps", [])
                    for call in step.get("tool_calls", [])
                ),
            },
            {
                "summary": f"{answer['_latency_ms']}ms",
                "latency_ms": answer["_latency_ms"],
            },
        )
        return answer

    def stage_mastery(self, attempts_before: int) -> list[str]:
        progress = _request(f"{self.base}/api/v1/courses/{self.course_id}/progress")
        topics = _request(f"{self.base}/api/v1/courses/{self.course_id}/topics")
        weak = [item["topic"] for item in topics if item.get("mastery_score", 1) < 0.6]
        self._record(
            "4-mastery",
            {
                "attempt_recorded": progress.get("total_attempts", 0) > attempts_before,
                "topics_present": bool(topics),
            },
            {
                "summary": f"{progress.get('total_attempts')} attempt(s), {len(topics)} topic(s)",
                "weak_topics": weak[:5],
            },
        )
        return weak

    def stage_plan(self) -> None:
        answer = self._chat("根据我的薄弱点帮我制定一份5天复习计划")
        trace = answer.get("trace", {})
        plans = _request(f"{self.base}/api/v1/courses/{self.course_id}/study-plans")
        created = any(
            call["name"] == "create_study_plan"
            for step in trace.get("steps", [])
            for call in step.get("tool_calls", [])
        )
        self._record(
            "5-plan",
            {
                "routed_to_planner": "planner" in trace.get("agent_sequence", []),
                "plan_created": created,
                "plan_persisted": bool(plans.get("items")),
            },
            {
                "summary": f"{len(plans.get('items', []))} plan(s), {answer['_latency_ms']}ms",
                "latency_ms": answer["_latency_ms"],
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the StudyPilot end-to-end loop evaluation.")
    parser.add_argument("--course-id", required=True)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--topic", default="残差")
    args = parser.parse_args()

    runner = LoopRunner(args.base_url, args.course_id)
    before = _request(f"{args.base_url}/api/v1/courses/{args.course_id}/progress")
    attempts_before = before.get("total_attempts", 0)

    runner.stage_explain(args.topic)
    runner.stage_practice()
    runner.stage_grade()
    runner.stage_mastery(attempts_before)
    runner.stage_plan()

    stages = runner.stages
    all_checks = [ok for stage in stages for ok in stage["checks"].values()]
    metrics = {
        "stage_count": len(stages),
        "stage_pass_rate": sum(1 for stage in stages if stage["passed"]) / len(stages),
        "check_pass_rate": sum(all_checks) / len(all_checks),
        "loop_closed": all(stage["passed"] for stage in stages),
        "total_latency_ms": sum(
            stage["detail"].get("latency_ms", 0) for stage in stages
        ),
    }
    report = {
        "dataset_version": DATASET_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "course_id": args.course_id,
        "metrics": metrics,
        "stages": stages,
    }
    output = Path("artifacts/evals")
    output.mkdir(parents=True, exist_ok=True)
    (output / "loop_latest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print()
    for key, value in metrics.items():
        print(f"{key}: {value}")
    print("\nWrote artifacts/evals/loop_latest.json")


if __name__ == "__main__":
    main()
