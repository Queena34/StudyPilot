from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.domain.models import Conversation
from app.llm.gateway import GeneratedAnswer
from app.rag.types import RetrievedEvidence
from app.schemas.tutor import TutorMessageCreate
from app.services.tutor_service import TutorService

USER_ID = UUID("00000000-0000-0000-0000-000000000001")
COURSE_ID = UUID("00000000-0000-0000-0000-000000000010")


def _evidence() -> RetrievedEvidence:
    return RetrievedEvidence(
        chunk_id="doc:0", document_id=str(uuid4()), filename="notes.pdf",
        page_number=3, section_title="Chapter 1",
        text="Least squares minimises the sum of squared residuals.", score=0.8,
    )


class _Gateway:
    """Cites nothing first, then obeys the reminder — the real failure shape."""

    def __init__(self, second: str | None) -> None:
        self.second = second
        self.reminders: list[bool] = []

    async def answer(self, **kwargs):
        self.reminders.append(bool(kwargs.get("citation_reminder")))
        if not kwargs.get("citation_reminder"):
            return GeneratedAnswer(answer="资料中没有相关内容。", model_name="m")
        if self.second is None:
            raise RuntimeError("provider down")
        return GeneratedAnswer(answer=self.second, model_name="m")


def _service(gateway) -> TutorService:
    conversation = Conversation(
        id=uuid4(), user_id=USER_ID, course_id=COURSE_ID, title="t"
    )
    return TutorService(
        course_repository=SimpleNamespace(get=AsyncMock(return_value=object())),
        conversation_repository=SimpleNamespace(
            get=AsyncMock(return_value=conversation),
            recent_messages=AsyncMock(return_value=[]),
            save_exchange=AsyncMock(),
        ),
        document_repository=SimpleNamespace(
            list_for_course=AsyncMock(return_value=[SimpleNamespace(id=uuid4(), language="en")])
        ),
        progress_repository=SimpleNamespace(),
        study_plan_repository=SimpleNamespace(),
        practice_service=SimpleNamespace(),
        retriever=SimpleNamespace(retrieve=AsyncMock(return_value=[_evidence()])),
        gateway=gateway,
        intent_router=SimpleNamespace(
            route=AsyncMock(return_value=_decision()),
        ),
    )


def _decision():
    from app.agents.routing import LearningIntent, QueryPlan, decision_for

    return decision_for(
        LearningIntent.COURSE_QA, confidence=0.9, reason="t",
        query_plan=QueryPlan(
            standalone_query="q", course_id=COURSE_ID, document_types=[], document_ids=[],
            page_from=None, page_to=None, requested_language="zh", top_k=8,
        ),
    )


async def test_an_uncited_answer_is_retried_before_being_discarded() -> None:
    gateway = _Gateway("资料中没有相关内容 [c1]。")
    result = await _service(gateway).answer(
        USER_ID, COURSE_ID, TutorMessageCreate(conversation_id=uuid4(), message="问题问题")
    )

    # A correct refusal cites nothing and used to be replaced by a passage dump.
    assert gateway.reminders == [False, True]
    assert "没有相关内容" in result.answer
    assert result.citations


async def test_the_extractive_fallback_still_applies_when_the_retry_also_fails() -> None:
    gateway = _Gateway("still no citation here")
    result = await _service(gateway).answer(
        USER_ID, COURSE_ID, TutorMessageCreate(conversation_id=uuid4(), message="问题问题")
    )

    assert gateway.reminders == [False, True]
    assert result.usage.model_name == "retrieval-fallback"


async def test_a_failing_retry_does_not_break_the_turn() -> None:
    gateway = _Gateway(None)
    result = await _service(gateway).answer(
        USER_ID, COURSE_ID, TutorMessageCreate(conversation_id=uuid4(), message="问题问题")
    )

    assert result.answer
    assert result.usage.model_name == "retrieval-fallback"


def test_every_fallback_reason_has_its_own_wording() -> None:
    """An unexplained degradation is indistinguishable from a normal answer."""

    import re
    from pathlib import Path

    from app.llm.gateway import FALLBACK_INTRODUCTIONS, UNKNOWN_FALLBACK

    root = Path(__file__).resolve().parents[2]
    source = "".join(
        (root / name).read_text(encoding="utf-8")
        for name in ("app/llm/gateway.py", "app/services/tutor_service.py")
    )
    used = set(re.findall(r'reason="([a-z_]+)"', source))

    assert used, "未找到任何 reason= 用法"
    missing = used - set(FALLBACK_INTRODUCTIONS)
    assert not missing, f"这些降级原因没有对应文案：{sorted(missing)}"


def test_an_unknown_reason_does_not_claim_the_request_failed() -> None:
    from app.llm.gateway import FALLBACK_INTRODUCTIONS, UNKNOWN_FALLBACK, _extractive_answer

    result = _extractive_answer([_evidence()], reason="something_new")

    # Defaulting to "the request failed" would state something untrue.
    assert FALLBACK_INTRODUCTIONS[UNKNOWN_FALLBACK] in result.answer
    assert "请求暂时失败" not in result.answer
    assert result.fallback_reason == "something_new"
