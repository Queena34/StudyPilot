from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.llm.gateway import _extractive_answer
from app.domain.models import Conversation, Message
from app.rag.types import RetrievedEvidence
from app.schemas.practice import Difficulty, QuestionType
from app.schemas.tutor import ResponseLanguage, TutorMessageCreate, TutorPracticeOptions, TutorScope
from app.services.tutor_service import (
    _conversation_title,
    _document_inventory_answer,
    _evidence_status,
    _document_learning_query,
    _latest_cited_document_ids,
    _latest_learning_request,
    _mentions_document_reference,
    _practice_configuration,
    _resolve_document_references,
    _remove_unknown_citations,
    _standalone_query,
    TutorService,
)


def _evidence(score: float = 0.8) -> RetrievedEvidence:
    return RetrievedEvidence(
        chunk_id="doc:0",
        document_id=str(UUID("00000000-0000-0000-0000-000000000003")),
        filename="lecture.md",
        page_number=1,
        section_title="Regularization",
        text="L1 regularization encourages sparse coefficients.",
        score=score,
    )


def test_scope_rejects_inverted_page_range() -> None:
    with pytest.raises(ValidationError):
        TutorScope(page_from=5, page_to=2)


def test_unknown_citations_are_removed() -> None:
    answer = _remove_unknown_citations("Supported [c1], invented [c9].", 2)

    assert answer == "Supported [c1], invented ."


def test_evidence_status_uses_retrieval_strength() -> None:
    assert _evidence_status([]) == "insufficient"
    assert _evidence_status([_evidence(0.1)]) == "partial"
    assert _evidence_status([_evidence(0.7)]) == "sufficient"


def test_extractive_fallback_keeps_real_citation() -> None:
    result = _extractive_answer([_evidence()])

    assert result.model_name == "retrieval-fallback"
    assert "[c1]" in result.answer


def test_citation_fallback_does_not_claim_model_is_unconfigured() -> None:
    result = _extractive_answer([_evidence()], reason="citation_validation_failed")

    assert "引用校验" in result.answer
    assert "未配置可用的大模型" not in result.answer
    assert result.fallback_reason == "citation_validation_failed"


def test_followup_query_includes_previous_question() -> None:
    history = [
        Message(
            user_id=UUID("00000000-0000-0000-0000-000000000001"),
            conversation_id=UUID("00000000-0000-0000-0000-000000000002"),
            role="user",
            content="L1 和 L2 正则化有什么区别？",
            citations_json=[],
        )
    ]

    query = _standalone_query("能举个例子吗？", history)

    assert "L1 和 L2" in query
    assert "能举个例子吗" in query


def test_continue_query_inherits_previous_chapter_request() -> None:
    history = [
        Message(
            user_id=UUID("00000000-0000-0000-0000-000000000001"),
            conversation_id=UUID("00000000-0000-0000-0000-000000000002"),
            role="user",
            content="详细讲解第一章",
            citations_json=[],
        ),
        Message(
            user_id=UUID("00000000-0000-0000-0000-000000000001"),
            conversation_id=UUID("00000000-0000-0000-0000-000000000002"),
            role="assistant",
            content="第一部分内容……",
            citations_json=[],
        ),
    ]

    query = _standalone_query("继续", history)

    assert "详细讲解第一章" in query
    assert "继续" in query


def test_new_short_question_is_not_forced_into_previous_topic() -> None:
    history = [
        Message(
            user_id=UUID("00000000-0000-0000-0000-000000000001"),
            conversation_id=UUID("00000000-0000-0000-0000-000000000002"),
            role="user",
            content="解释正则化",
            citations_json=[],
        )
    ]

    assert _standalone_query("什么是 PCA？", history) == "什么是 PCA？"


def test_conversation_title_is_single_line_and_bounded() -> None:
    assert _conversation_title("  First line\nsecond line  ") == "First line second line"
    assert len(_conversation_title("a" * 200)) == 80


def test_document_inventory_answer_includes_every_document() -> None:
    documents = [
        SimpleNamespace(
            filename="second.pdf", status="ready", page_count=6, chunk_count=70
        ),
        SimpleNamespace(
            filename="first.pdf", status="ready", page_count=6, chunk_count=146
        ),
    ]

    answer = _document_inventory_answer(documents, "zh")

    assert "2 份课程资料" in answer
    assert "first.pdf" in answer
    assert "second.pdf" in answer
    assert "146 个知识片段" in answer


def test_practice_configuration_is_parsed_from_natural_language() -> None:
    configuration = _practice_configuration(
        "针对薄弱点给我出 5 道困难选择题",
        ResponseLanguage.ZH,
        TutorScope(),
    )

    assert configuration.question_count == 5
    assert configuration.question_type == QuestionType.SINGLE_CHOICE
    assert configuration.difficulty == Difficulty.ADVANCED
    assert configuration.prioritize_weak_topics is True


def test_chat_practice_options_default_to_selected_multiple_choice_settings() -> None:
    configuration = _practice_configuration(
        "针对已经学的内容生成练习",
        ResponseLanguage.ZH,
        TutorScope(),
        options=TutorPracticeOptions(
            question_type="single_choice", difficulty="advanced", question_count=5
        ),
        context_topic="详细讲解第一章",
    )

    assert configuration.question_type == QuestionType.SINGLE_CHOICE
    assert configuration.difficulty == Difficulty.ADVANCED
    assert configuration.question_count == 5
    assert configuration.topic == "详细讲解第一章"


def test_learned_context_restores_chapter_and_cited_document() -> None:
    document_id = UUID("00000000-0000-0000-0000-000000000099")
    history = [
        Message(
            user_id=UUID("00000000-0000-0000-0000-000000000001"),
            conversation_id=UUID("00000000-0000-0000-0000-000000000002"),
            role="user",
            content="详细讲解第一章",
            citations_json=[],
        ),
        Message(
            user_id=UUID("00000000-0000-0000-0000-000000000001"),
            conversation_id=UUID("00000000-0000-0000-0000-000000000002"),
            role="assistant",
            content="第一章讲解",
            citations_json=[{"document_id": str(document_id)}],
        ),
    ]

    assert _latest_learning_request(history) == "详细讲解第一章"
    assert _latest_cited_document_ids(history) == [document_id]


@pytest.mark.asyncio
async def test_practice_agent_receives_recent_learned_scope_and_selected_options() -> None:
    user_id = UUID("00000000-0000-0000-0000-000000000001")
    course_id = UUID("00000000-0000-0000-0000-000000000002")
    conversation_id = UUID("00000000-0000-0000-0000-000000000003")
    document_id = UUID("00000000-0000-0000-0000-000000000099")
    history = [
        Message(user_id=user_id, conversation_id=conversation_id, role="user", content="详细讲解第一章", citations_json=[]),
        Message(
            user_id=user_id,
            conversation_id=conversation_id,
            role="assistant",
            content="第一章讲解",
            citations_json=[{"document_id": str(document_id)}],
        ),
    ]
    course_repository = SimpleNamespace(get=AsyncMock(return_value=object()))
    conversation_repository = SimpleNamespace(
        get=AsyncMock(return_value=Conversation(id=conversation_id, user_id=user_id, course_id=course_id, title="第一章")),
        recent_messages=AsyncMock(return_value=history),
        save_exchange=AsyncMock(),
    )
    created_practice = SimpleNamespace(
        title="第一章练习",
        questions=[object()] * 5,
        model_name="fake-quiz",
        model_dump=lambda mode=None: {"title": "第一章练习", "questions": []},
    )
    practice_service = SimpleNamespace(create=AsyncMock(return_value=created_practice))
    service = TutorService(
        course_repository=course_repository,
        conversation_repository=conversation_repository,
        document_repository=SimpleNamespace(),
        progress_repository=SimpleNamespace(),
        study_plan_repository=SimpleNamespace(),
        practice_service=practice_service,
    )

    await service.answer(
        user_id,
        course_id,
        TutorMessageCreate(
            conversation_id=conversation_id,
            message="针对已经学的内容生成练习",
            practice_options=TutorPracticeOptions(
                question_type="single_choice", difficulty="advanced", question_count=5
            ),
        ),
    )

    configuration = practice_service.create.await_args.args[2]
    assert configuration.topic == "详细讲解第一章"
    assert configuration.scope.document_ids == [document_id]
    assert configuration.question_type == QuestionType.SINGLE_CHOICE
    assert configuration.difficulty == Difficulty.ADVANCED
    assert configuration.question_count == 5


def test_resolves_document_ordinal_by_upload_order() -> None:
    first_id = UUID("00000000-0000-0000-0000-000000000031")
    second_id = UUID("00000000-0000-0000-0000-000000000032")
    documents_newest_first = [
        SimpleNamespace(id=second_id, filename="second.pdf"),
        SimpleNamespace(id=first_id, filename="first.pdf"),
    ]

    assert _resolve_document_references("开始学习资料1", documents_newest_first) == [first_id]
    assert _resolve_document_references("总结第二份 PDF", documents_newest_first) == [second_id]
    assert _resolve_document_references("Use second.pdf", documents_newest_first) == [second_id]


def test_document_reference_detection_and_learning_query() -> None:
    assert _mentions_document_reference("先开始学习资料1")
    assert not _mentions_document_reference("什么是线性模型？")
    query = _document_learning_query("先开始学习资料1", "先开始学习资料1")
    assert "most important concepts" in query
