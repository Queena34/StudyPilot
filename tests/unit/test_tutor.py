from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.llm.gateway import _extractive_answer
from app.domain.models import Message
from app.rag.types import RetrievedEvidence
from app.schemas.practice import Difficulty, QuestionType
from app.schemas.tutor import ResponseLanguage, TutorScope
from app.services.tutor_service import (
    _conversation_title,
    _document_inventory_answer,
    _evidence_status,
    _practice_configuration,
    _remove_unknown_citations,
    _standalone_query,
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
