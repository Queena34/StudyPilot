from datetime import datetime, timezone
from math import isclose
from uuid import UUID

from app.core.exceptions import AppError, ResourceNotFoundError
from app.domain.models import PracticeSet, Question
from app.infrastructure.repositories.course_repository import CourseRepository
from app.infrastructure.repositories.practice_repository import PracticeRepository
from app.llm.quiz_gateway import QuizGenerationGateway
from app.rag.retrieval import CourseRetriever
from app.rag.types import RetrievedEvidence
from app.schemas.practice import (
    GeneratedQuestion,
    PracticeQuestionRead,
    PracticeSetCreate,
    PracticeSetRead,
    QuestionOption,
    QuestionType,
)
from app.schemas.tutor import Citation


class PracticeService:
    def __init__(
        self,
        course_repository: CourseRepository,
        practice_repository: PracticeRepository,
        retriever: CourseRetriever | None = None,
        gateway: QuizGenerationGateway | None = None,
    ) -> None:
        self.course_repository = course_repository
        self.practice_repository = practice_repository
        self.retriever = retriever or CourseRetriever()
        self.gateway = gateway or QuizGenerationGateway()

    async def create(
        self, user_id: UUID, course_id: UUID, data: PracticeSetCreate
    ) -> PracticeSetRead:
        if await self.course_repository.get(user_id, course_id) is None:
            raise ResourceNotFoundError("课程")
        scope = data.scope
        evidence = await self.retriever.retrieve(
            user_id=user_id,
            course_id=course_id,
            query=data.topic or "important course concepts definitions and relationships",
            top_k=max(8, data.question_count * 2),
            document_types=[item.value for item in scope.document_types] or None,
            document_ids=scope.document_ids or None,
            page_from=scope.page_from,
            page_to=scope.page_to,
        )
        if not evidence:
            raise AppError(
                "INSUFFICIENT_EVIDENCE",
                "选定范围内没有足够的课程资料用于出题",
                status_code=422,
            )
        generated, model_name = await self.gateway.generate(
            question_type=data.question_type,
            difficulty=data.difficulty,
            count=data.question_count,
            language=data.language.value,
            topic=data.topic,
            evidence=evidence,
        )
        _validate_questions(generated, data, len(evidence))
        source_map = _source_map(evidence)
        practice_set = PracticeSet(
            user_id=user_id,
            course_id=course_id,
            title=data.title or f"{data.topic or '课程资料'}练习",
            status="ready",
            configuration_json=data.model_dump(mode="json"),
            model_name=model_name,
            completed_at=datetime.now(timezone.utc),
        )
        for item in generated:
            practice_set.questions.append(
                Question(
                    course_id=course_id,
                    question_type=item.question_type.value,
                    difficulty=item.difficulty.value,
                    content=item.content,
                    options_json=(
                        [option.model_dump() for option in item.options] if item.options else None
                    ),
                    knowledge_points_json=item.knowledge_points,
                    reference_answer=item.reference_answer,
                    rubric_json=[rubric.model_dump() for rubric in item.rubric],
                    source_refs_json=[
                        source_map[value] for value in _question_evidence_ids(item)
                    ],
                    generation_metadata_json={"model_name": model_name, "prompt_version": 1},
                )
            )
        await self.practice_repository.create(practice_set)
        return _to_read(practice_set)

    async def get(self, user_id: UUID, practice_set_id: UUID) -> PracticeSetRead:
        practice_set = await self.practice_repository.get(user_id, practice_set_id)
        if practice_set is None:
            raise ResourceNotFoundError("练习集")
        return _to_read(practice_set)


def _validate_questions(
    questions: list[GeneratedQuestion], data: PracticeSetCreate, evidence_count: int
) -> None:
    if len(questions) != data.question_count:
        raise AppError("INVALID_GENERATED_QUESTIONS", "生成题目数量不符合要求", status_code=503)
    if len({item.content.strip().casefold() for item in questions}) != len(questions):
        raise AppError("DUPLICATE_GENERATED_QUESTIONS", "生成结果包含重复题目", status_code=503)
    allowed_evidence = {f"c{index}" for index in range(1, evidence_count + 1)}
    for item in questions:
        if item.question_type != data.question_type or item.difficulty != data.difficulty:
            raise AppError("INVALID_GENERATED_QUESTIONS", "生成题型或难度不符合要求", status_code=503)
        referenced = set(item.evidence_ids)
        referenced.update(value for rubric in item.rubric for value in rubric.evidence_ids)
        if not referenced or not referenced <= allowed_evidence:
            raise AppError("INVALID_GENERATED_CITATION", "生成题目包含无效资料引用", status_code=503)
        if not isclose(sum(rubric.weight for rubric in item.rubric), 1.0, abs_tol=0.001):
            raise AppError("INVALID_GENERATED_RUBRIC", "题目评分标准权重不等于1", status_code=503)
        if item.question_type == QuestionType.SINGLE_CHOICE:
            if item.options is None or len(item.options) != 4:
                raise AppError("INVALID_GENERATED_OPTIONS", "选择题必须有四个选项", status_code=503)
            if sum(option.is_correct for option in item.options) != 1:
                raise AppError("INVALID_GENERATED_OPTIONS", "选择题必须仅有一个正确答案", status_code=503)
        elif item.options is not None:
            raise AppError("INVALID_GENERATED_OPTIONS", "非选择题不能包含选项", status_code=503)


def _source_map(evidence: list[RetrievedEvidence]) -> dict[str, dict]:
    return {
        f"c{index}": Citation(
            citation_id=f"c{index}",
            document_id=item.document_id,
            filename=item.filename,
            page_number=item.page_number,
            section_title=item.section_title,
            snippet=item.text[:300],
            chunk_id=item.chunk_id,
            score=round(item.score, 4),
        ).model_dump(mode="json")
        for index, item in enumerate(evidence, start=1)
    }


def _question_evidence_ids(question: GeneratedQuestion) -> list[str]:
    values = question.evidence_ids + [
        value for rubric in question.rubric for value in rubric.evidence_ids
    ]
    return list(dict.fromkeys(values))


def _to_read(practice_set: PracticeSet) -> PracticeSetRead:
    return PracticeSetRead(
        id=practice_set.id,
        course_id=practice_set.course_id,
        title=practice_set.title,
        status=practice_set.status,
        configuration=practice_set.configuration_json,
        model_name=practice_set.model_name,
        created_at=practice_set.created_at,
        completed_at=practice_set.completed_at,
        questions=[
            PracticeQuestionRead(
                id=item.id,
                question_type=item.question_type,
                difficulty=item.difficulty,
                content=item.content,
                options=(
                    [QuestionOption(id=value["id"], text=value["text"]) for value in item.options_json]
                    if item.options_json
                    else None
                ),
                knowledge_points=item.knowledge_points_json,
                sources=[Citation.model_validate(value) for value in item.source_refs_json],
            )
            for item in practice_set.questions
        ],
    )
