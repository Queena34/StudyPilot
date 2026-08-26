from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.core.exceptions import AppError, ResourceNotFoundError
from app.domain.models import DocumentStatus
from app.services.document_service import DocumentService
from app.services.practice_service import PracticeService, _to_summary


COURSE_ID = UUID("00000000-0000-0000-0000-000000000010")
USER_ID = UUID("00000000-0000-0000-0000-000000000011")


def _question(question_id: UUID):
    return SimpleNamespace(id=question_id)


def _practice_set(question_ids, *, topic=None, question_type="short_answer"):
    return SimpleNamespace(
        id=uuid4(),
        title="课程资料练习",
        status="ready",
        configuration_json={
            "question_type": question_type,
            "difficulty": "medium",
            "topic": topic,
        },
        questions=[_question(item) for item in question_ids],
        created_at=datetime.now(timezone.utc),
    )


def test_summary_counts_only_questions_that_were_actually_answered() -> None:
    first, second, third = uuid4(), uuid4(), uuid4()
    practice_set = _practice_set([first, second, third])

    summary = _to_summary(practice_set, {first: 90.0, second: 40.0}, 60.0)

    assert summary.question_count == 3
    assert summary.answered_count == 2
    assert summary.average_score == 65.0


def test_summary_flags_low_scoring_questions_for_retry() -> None:
    first, second, third = uuid4(), uuid4(), uuid4()
    practice_set = _practice_set([first, second, third])

    summary = _to_summary(practice_set, {first: 100.0, second: 60.0, third: 20.0}, 60.0)

    # 60 is the threshold and still needs work; 100 does not.
    assert summary.incorrect_count == 2


def test_summary_reports_no_score_before_anything_is_answered() -> None:
    practice_set = _practice_set([uuid4(), uuid4()])

    summary = _to_summary(practice_set, {}, 60.0)

    assert summary.answered_count == 0
    assert summary.incorrect_count == 0
    assert summary.average_score is None


def test_summary_never_exposes_answers_or_rubric() -> None:
    summary = _to_summary(_practice_set([uuid4()]), {}, 60.0)
    payload = summary.model_dump()

    # The history list is visible before answering, so it must not leak solutions.
    assert "reference_answer" not in payload
    assert "rubric" not in payload
    assert "questions" not in payload


async def test_listing_practice_sets_requires_owning_the_course() -> None:
    service = PracticeService(
        SimpleNamespace(get=_async(None)), SimpleNamespace()
    )

    with pytest.raises(ResourceNotFoundError):
        await service.list_for_course(USER_ID, COURSE_ID, page=1, size=20)


async def test_listing_practice_sets_scores_each_set() -> None:
    first, second = uuid4(), uuid4()
    practice_set = _practice_set([first, second])
    repository = SimpleNamespace(
        list_for_course=_async([practice_set]),
        best_scores_for_questions=_async({first: 80.0, second: 30.0}),
    )
    service = PracticeService(SimpleNamespace(get=_async(object())), repository)

    result = await service.list_for_course(USER_ID, COURSE_ID, page=1, size=20)

    assert result.page == 1
    assert len(result.items) == 1
    assert result.items[0].answered_count == 2
    assert result.items[0].incorrect_count == 1


async def test_only_a_failed_document_can_be_reprocessed() -> None:
    document = SimpleNamespace(id=uuid4(), status=DocumentStatus.READY.value)
    service = DocumentService(
        SimpleNamespace(get=_async(document)), SimpleNamespace(), SimpleNamespace()
    )

    with pytest.raises(AppError) as error:
        await service.reprocess(USER_ID, document.id)

    # Reprocessing a healthy document would duplicate its chunks.
    assert error.value.code == "DOCUMENT_NOT_RETRYABLE"


async def test_reprocessing_a_failed_document_queues_a_new_job() -> None:
    document = SimpleNamespace(
        id=uuid4(), status=DocumentStatus.FAILED.value, error_message="parser failed"
    )
    queued: dict = {}

    async def requeue(doc, job):
        queued["document"] = doc
        queued["job"] = job
        return job

    service = DocumentService(
        SimpleNamespace(get=_async(document), requeue=requeue),
        SimpleNamespace(),
        SimpleNamespace(),
    )

    _, job = await service.reprocess(USER_ID, document.id)

    assert job.job_type == "document_ingestion"
    assert queued["document"] is document


async def test_reprocessing_a_missing_document_is_not_found() -> None:
    service = DocumentService(
        SimpleNamespace(get=_async(None)), SimpleNamespace(), SimpleNamespace()
    )

    with pytest.raises(ResourceNotFoundError):
        await service.reprocess(USER_ID, uuid4())


def _async(value):
    async def call(*args, **kwargs):
        return value

    return call
