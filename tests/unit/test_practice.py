from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.core.exceptions import AppError
from app.llm.quiz_gateway import (
    _fallback_questions,
    _matches_generation_request,
    _parse_support_decision,
)
from app.rag.types import RetrievedEvidence
from app.schemas.practice import (
    Difficulty,
    GeneratedOption,
    GeneratedQuestion,
    PracticeSetCreate,
    QuestionType,
    RubricItem,
)
from app.services.practice_service import PracticeService, _validate_questions


def _evidence() -> RetrievedEvidence:
    return RetrievedEvidence(
        chunk_id="doc:0",
        document_id=str(UUID("00000000-0000-0000-0000-000000000003")),
        filename="lecture.md",
        page_number=1,
        section_title="Regularization",
        text="L1 regularization can create sparse coefficients.",
        score=0.8,
    )


def test_fallback_single_choice_has_one_correct_option_and_source() -> None:
    questions = _fallback_questions(
        QuestionType.SINGLE_CHOICE, Difficulty.MEDIUM, 2, [_evidence()]
    )

    assert len(questions) == 2
    assert all(len(item.options or []) == 4 for item in questions)
    assert all(sum(option.is_correct for option in item.options or []) == 1 for item in questions)
    assert all(item.evidence_ids == ["c1"] for item in questions)
    assert len({item.content for item in questions}) == 2


def test_validator_rejects_multiple_correct_options() -> None:
    question = GeneratedQuestion(
        question_type=QuestionType.SINGLE_CHOICE,
        difficulty=Difficulty.BASIC,
        content="Which statement is correct?",
        options=[
            GeneratedOption(id="A", text="A", is_correct=True),
            GeneratedOption(id="B", text="B", is_correct=True),
            GeneratedOption(id="C", text="C", is_correct=False),
            GeneratedOption(id="D", text="D", is_correct=False),
        ],
        knowledge_points=["topic"],
        reference_answer="A",
        rubric=[
            RubricItem(
                criterion="correct",
                weight=1,
                required_concepts=["topic"],
                evidence_ids=["c1"],
            )
        ],
        evidence_ids=["c1"],
    )
    request = PracticeSetCreate(
        question_type=QuestionType.SINGLE_CHOICE,
        difficulty=Difficulty.BASIC,
        question_count=1,
    )

    with pytest.raises(AppError) as exc_info:
        _validate_questions([question], request, 1)

    assert exc_info.value.code == "INVALID_GENERATED_OPTIONS"


def test_validator_rejects_unknown_evidence() -> None:
    question = _fallback_questions(
        QuestionType.CONCEPT, Difficulty.ADVANCED, 1, [_evidence()]
    )[0]
    question.evidence_ids = ["c9"]
    request = PracticeSetCreate(
        question_type=QuestionType.CONCEPT,
        difficulty=Difficulty.ADVANCED,
        question_count=1,
    )

    with pytest.raises(AppError) as exc_info:
        _validate_questions([question], request, 1)

    assert exc_info.value.code == "INVALID_GENERATED_CITATION"


def test_generation_request_match_rejects_wrong_type_or_difficulty() -> None:
    questions = _fallback_questions(
        QuestionType.CONCEPT, Difficulty.MEDIUM, 1, [_evidence()]
    )

    assert _matches_generation_request(
        questions, QuestionType.CONCEPT, Difficulty.MEDIUM, 1
    )
    assert not _matches_generation_request(
        questions, QuestionType.SHORT_ANSWER, Difficulty.MEDIUM, 1
    )
    assert not _matches_generation_request(
        questions, QuestionType.CONCEPT, Difficulty.ADVANCED, 1
    )


def test_generation_request_match_rejects_empty_unsupported_result() -> None:
    assert not _matches_generation_request(
        [], QuestionType.CONCEPT, Difficulty.MEDIUM, 1
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"supported": true}', True),
        ('```json\n{"supported": false}\n```', False),
        ('{"supported": "yes"}', None),
        ("not-json", None),
    ],
)
def test_parse_topic_support_decision(text: str, expected: bool | None) -> None:
    assert _parse_support_decision(text) is expected


@pytest.mark.asyncio
async def test_practice_service_rejects_topic_unsupported_by_sources() -> None:
    course_repository = SimpleNamespace(get=AsyncMock(return_value=object()))
    practice_repository = SimpleNamespace(create=AsyncMock())
    retriever = SimpleNamespace(retrieve=AsyncMock(return_value=[_evidence()]))
    gateway = SimpleNamespace(
        expand_query=AsyncMock(return_value="Transformer transformer multi-head attention"),
        generate=AsyncMock(return_value=([], "test-model")),
    )
    service = PracticeService(
        course_repository,
        practice_repository,
        retriever=retriever,
        gateway=gateway,
    )

    with pytest.raises(AppError) as exc_info:
        await service.create(
            UUID("00000000-0000-0000-0000-000000000001"),
            UUID("00000000-0000-0000-0000-000000000002"),
            PracticeSetCreate(topic="Transformer", question_count=1),
        )

    assert exc_info.value.code == "INSUFFICIENT_EVIDENCE"
    assert retriever.retrieve.await_args.kwargs["query"] == (
        "Transformer transformer multi-head attention"
    )
    practice_repository.create.assert_not_awaited()
