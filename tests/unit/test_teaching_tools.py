from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.agents.protocol import LearningContext
from app.agents.routing import LearningIntent, QueryPlan, decision_for
from app.agents.tools import TeachingToolManager, ToolPermissionError
from app.core.exceptions import AppError, ResourceNotFoundError
from app.schemas.tutor import TutorScope


COURSE_ID = UUID("00000000-0000-0000-0000-000000000010")
USER_ID = UUID("00000000-0000-0000-0000-000000000011")
OWN_DOCUMENT = UUID("00000000-0000-0000-0000-0000000000a1")
OTHER_DOCUMENT = UUID("00000000-0000-0000-0000-0000000000b2")


def _async(value):
    async def call(*args, **kwargs):
        return value

    return call


def _raises(error: Exception):
    async def call(*args, **kwargs):
        raise error

    return call


class _CountingRetriever:
    def __init__(self) -> None:
        self.calls = 0

    async def retrieve(self, **kwargs):
        self.calls += 1
        self.last = kwargs
        return [SimpleNamespace(text="chunk")]


def _manager(**overrides) -> TeachingToolManager:
    defaults = dict(
        course_repository=SimpleNamespace(get=_async(object())),
        document_repository=SimpleNamespace(
            list_for_course=_async([SimpleNamespace(id=OWN_DOCUMENT)])
        ),
        progress_repository=SimpleNamespace(),
        study_plan_repository=SimpleNamespace(),
        retriever=_CountingRetriever(),
        practice_service=SimpleNamespace(),
    )
    defaults.update(overrides)
    return TeachingToolManager(**defaults)


def _context(tools: TeachingToolManager) -> LearningContext:
    plan = QueryPlan(
        standalone_query="q",
        course_id=COURSE_ID,
        document_types=[],
        document_ids=[],
        page_from=None,
        page_to=None,
        requested_language="zh",
        top_k=8,
    )
    return LearningContext(
        user_id=USER_ID,
        course_id=COURSE_ID,
        conversation_id=uuid4(),
        message="m",
        language="zh",
        mode="standard",
        scope=TutorScope(),
        decision=decision_for(
            LearningIntent.COURSE_QA, confidence=0.9, reason="t", query_plan=plan
        ),
        tools=tools,
    )


async def _search(session, context, document_ids=None):
    return await session.search_course_material(
        context,
        query="q",
        top_k=8,
        document_types=[],
        document_ids=document_ids,
        page_from=None,
        page_to=None,
    )


async def test_search_rejects_a_document_from_another_course() -> None:
    tools = _manager()
    context = _context(tools)

    with pytest.raises(ToolPermissionError):
        await _search(tools.session(), context, [OTHER_DOCUMENT])

    # The retriever must never be reached once the scope check fails.
    assert tools.retriever.calls == 0


async def test_search_allows_a_document_belonging_to_the_course() -> None:
    tools = _manager()
    context = _context(tools)

    await _search(tools.session(), context, [OWN_DOCUMENT])

    assert tools.retriever.calls == 1
    assert tools.retriever.last["document_ids"] == [OWN_DOCUMENT]


async def test_tools_refuse_a_course_the_caller_does_not_own() -> None:
    tools = _manager(course_repository=SimpleNamespace(get=_async(None)))
    context = _context(tools)

    with pytest.raises(ResourceNotFoundError):
        await tools.session().list_course_documents(context)


async def test_authorization_is_cached_across_calls() -> None:
    lookups = {"count": 0}

    async def get(user_id, course_id):
        lookups["count"] += 1
        return object()

    tools = _manager(course_repository=SimpleNamespace(get=get))
    context = _context(tools)
    session = tools.session()

    await session.list_course_documents(context)
    await session.list_course_documents(context)

    assert lookups["count"] == 1


async def test_successful_calls_are_recorded_with_latency_and_detail() -> None:
    tools = _manager()
    context = _context(tools)
    session = tools.session()

    await _search(session, context)

    call = session.calls[0]
    assert call.name == "search_course_material"
    assert call.ok is True
    assert call.detail == "1 chunk(s)"
    assert call.latency_ms >= 0


async def test_failing_calls_are_recorded_with_their_reason_and_reraised() -> None:
    class _Boom:
        async def retrieve(self, **kwargs):
            raise AppError("VECTOR_STORE_DOWN", "檢索不可用")

    tools = _manager(retriever=_Boom())
    context = _context(tools)
    session = tools.session()

    with pytest.raises(AppError):
        await _search(session, context)

    assert session.calls[0].ok is False
    assert session.calls[0].detail == "VECTOR_STORE_DOWN"


async def test_each_session_records_only_its_own_calls() -> None:
    tools = _manager()
    context = _context(tools)
    first, second = tools.session(), tools.session()

    await _search(first, context)

    assert len(first.calls) == 1
    assert second.calls == []


async def test_unconfigured_tools_are_denied_rather_than_crashing() -> None:
    tools = _manager()
    context = _context(tools)

    with pytest.raises(ToolPermissionError):
        await tools.session().create_study_plan(context, SimpleNamespace())
    with pytest.raises(ToolPermissionError):
        await tools.session().grade_answer(context, uuid4(), SimpleNamespace())


async def test_practice_creation_validates_the_requested_document_scope() -> None:
    tools = _manager(practice_service=SimpleNamespace(create=_async(object())))
    context = _context(tools)
    configuration = SimpleNamespace(scope=TutorScope(document_ids=[OTHER_DOCUMENT]))

    with pytest.raises(ToolPermissionError):
        await tools.session().create_practice_set(context, configuration)
