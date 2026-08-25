import re
from time import monotonic
from uuid import UUID, uuid4

from app.core.exceptions import AppError, ResourceNotFoundError
from app.domain.models import Conversation, Message
from app.infrastructure.repositories.conversation_repository import ConversationRepository
from app.infrastructure.repositories.course_repository import CourseRepository
from app.llm.gateway import TutorAnswerGateway, _extractive_answer
from app.rag.retrieval import CourseRetriever
from app.schemas.tutor import Citation, TokenUsage, TutorMessageCreate, TutorMessageRead


class TutorService:
    def __init__(
        self,
        course_repository: CourseRepository,
        conversation_repository: ConversationRepository,
        retriever: CourseRetriever | None = None,
        gateway: TutorAnswerGateway | None = None,
    ) -> None:
        self.course_repository = course_repository
        self.conversation_repository = conversation_repository
        self.retriever = retriever or CourseRetriever()
        self.gateway = gateway or TutorAnswerGateway()

    async def answer(
        self, user_id: UUID, course_id: UUID, data: TutorMessageCreate
    ) -> TutorMessageRead:
        if await self.course_repository.get(user_id, course_id) is None:
            raise ResourceNotFoundError("课程")

        history: list[Message] = []
        if data.conversation_id is None:
            conversation = Conversation(
                id=uuid4(),
                user_id=user_id,
                course_id=course_id,
                title=_conversation_title(data.message),
            )
        else:
            conversation = await self.conversation_repository.get(
                user_id, course_id, data.conversation_id
            )
            if conversation is None:
                raise ResourceNotFoundError("对话")
            history = await self.conversation_repository.recent_messages(
                user_id, conversation.id
            )

        scope = data.scope
        retrieval_query = _standalone_query(data.message, history)
        started = monotonic()
        evidence = await self.retriever.retrieve(
            user_id=user_id,
            course_id=course_id,
            query=retrieval_query,
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
            history=[(item.role, item.content) for item in history],
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
        latency_ms = round((monotonic() - started) * 1000)
        assistant_message_id = uuid4()
        await self.conversation_repository.save_exchange(
            conversation=conversation,
            user_message=Message(
                user_id=user_id,
                conversation_id=conversation.id,
                role="user",
                content=data.message,
                agent_type="tutor",
                citations_json=[],
                latency_ms=None,
            ),
            assistant_message=Message(
                id=assistant_message_id,
                user_id=user_id,
                conversation_id=conversation.id,
                role="assistant",
                content=answer,
                agent_type="tutor",
                citations_json=[item.model_dump(mode="json") for item in citations],
                model_name=generated.model_name,
                latency_ms=latency_ms,
            ),
        )
        return TutorMessageRead(
            message_id=assistant_message_id,
            conversation_id=conversation.id,
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


def _conversation_title(message: str) -> str:
    return " ".join(message.split())[:80]


def _standalone_query(message: str, history: list[Message]) -> str:
    if not history:
        return message
    normalized = message.strip().lower()
    followup_markers = (
        "它",
        "这个",
        "这些",
        "上述",
        "刚才",
        "再",
        "举个例子",
        "what about",
        "it",
        "this",
        "that",
        "example",
    )
    if not any(marker in normalized for marker in followup_markers):
        return message
    previous_question = next(
        (item.content for item in reversed(history) if item.role == "user"), None
    )
    return f"{previous_question}\nFollow-up: {message}" if previous_question else message
