import re
from uuid import UUID, uuid4

from app.core.exceptions import AppError, ResourceNotFoundError
from app.infrastructure.repositories.course_repository import CourseRepository
from app.llm.gateway import TutorAnswerGateway, _extractive_answer
from app.rag.retrieval import CourseRetriever
from app.schemas.tutor import Citation, TokenUsage, TutorMessageCreate, TutorMessageRead


class TutorService:
    def __init__(
        self,
        course_repository: CourseRepository,
        retriever: CourseRetriever | None = None,
        gateway: TutorAnswerGateway | None = None,
    ) -> None:
        self.course_repository = course_repository
        self.retriever = retriever or CourseRetriever()
        self.gateway = gateway or TutorAnswerGateway()

    async def answer(
        self, user_id: UUID, course_id: UUID, data: TutorMessageCreate
    ) -> TutorMessageRead:
        if await self.course_repository.get(user_id, course_id) is None:
            raise ResourceNotFoundError("课程")

        scope = data.scope
        evidence = await self.retriever.retrieve(
            user_id=user_id,
            course_id=course_id,
            query=data.message,
            top_k=8,
            document_types=[item.value for item in scope.document_types] or None,
            document_ids=scope.document_ids or None,
            page_from=scope.page_from,
            page_to=scope.page_to,
        )
        status = _evidence_status(evidence)
        generated = await self.gateway.answer(
            question=data.message,
            language=data.response_language.value,
            mode=data.mode.value,
            evidence=evidence,
        )
        answer = _remove_unknown_citations(generated.answer, len(evidence))
        cited = {int(value) for value in re.findall(r"\[c(\d+)]", answer)}
        if evidence and not cited:
            generated = _extractive_answer(evidence)
            answer = generated.answer
            cited = {int(value) for value in re.findall(r"\[c(\d+)]", answer)}
        citations = [
            Citation(
                citation_id=f"c{index}",
                document_id=item.document_id,
                filename=item.filename,
                page_number=item.page_number,
                section_title=item.section_title,
                snippet=item.text[:300],
                chunk_id=item.chunk_id,
                score=round(item.score, 4),
            )
            for index, item in enumerate(evidence, start=1)
            if index in cited
        ]
        conversation_id = data.conversation_id or uuid4()
        return TutorMessageRead(
            message_id=uuid4(),
            conversation_id=conversation_id,
            answer=answer,
            citations=citations,
            evidence_status=status,
            suggested_followups=_followups(status),
            usage=TokenUsage(
                model_name=generated.model_name,
                input_tokens=generated.input_tokens,
                output_tokens=generated.output_tokens,
            ),
        )


def _evidence_status(evidence: list) -> str:
    if not evidence:
        return "insufficient"
    if evidence[0].score >= 0.2 or len(evidence) >= 2 and evidence[1].score >= 0.15:
        return "sufficient"
    return "partial"


def _remove_unknown_citations(answer: str, evidence_count: int) -> str:
    def replace(match: re.Match) -> str:
        index = int(match.group(1))
        return match.group(0) if 1 <= index <= evidence_count else ""

    cleaned = re.sub(r"\[c(\d+)]", replace, answer)
    if not cleaned.strip():
        raise AppError("ANSWER_GENERATION_FAILED", "暂时无法生成可靠回答", status_code=503)
    return cleaned


def _followups(status: str) -> list[str]:
    if status == "insufficient":
        return ["要不要换一个关键词提问？", "是否需要上传更多课程资料？"]
    return ["能否用一个具体例子说明？", "请根据这些内容出一道练习题。"]
