import re
from time import monotonic
from uuid import UUID, uuid4

from app.agents.intent_router import LearningIntentRouter
from app.agents.learning_agents import (
    CatalogAgent,
    ClarifyAgent,
    EvaluatorAgent,
    IntegrityGuardAgent,
    GeneralAgent,
    PlannerAgent,
    ProgressAgent,
    QuizAgent,
    TutorAgent,
)
from app.agents.orchestrator import LearningAgentOrchestrator
from app.agents.presenters import (
    CITATION_SNIPPET_LIMIT,
    _followups,
    _remove_unknown_citations,
)
from app.agents.integrity import AcademicIntegrityGuard
from app.agents.protocol import LearningContext
from app.agents.tools import TeachingToolManager
from app.agents.routing import AgentName
from app.core.exceptions import AppError, ResourceNotFoundError
from app.domain.models import Conversation, Document, Message
from app.infrastructure.repositories.conversation_repository import ConversationRepository
from app.infrastructure.repositories.course_repository import CourseRepository
from app.infrastructure.repositories.document_repository import DocumentRepository
from app.infrastructure.repositories.progress_repository import ProgressRepository
from app.infrastructure.repositories.study_plan_repository import StudyPlanRepository
from app.llm.gateway import GeneratedAnswer, TutorAnswerGateway, _extractive_answer
from app.rag.retrieval import CourseRetriever
from app.schemas.tutor import Citation, TokenUsage, TutorMessageCreate, TutorMessageRead
from app.schemas.practice import Difficulty, PracticeSetCreate, QuestionType
from app.services.practice_service import PracticeService


class TutorService:
    def __init__(
        self,
        course_repository: CourseRepository,
        conversation_repository: ConversationRepository,
        document_repository: DocumentRepository,
        progress_repository: ProgressRepository,
        study_plan_repository: StudyPlanRepository,
        practice_service: PracticeService,
        attempt_service=None,
        study_plan_service=None,
        practice_repository=None,
        retriever: CourseRetriever | None = None,
        gateway: TutorAnswerGateway | None = None,
        intent_router: LearningIntentRouter | None = None,
        orchestrator: LearningAgentOrchestrator | None = None,
        tools: TeachingToolManager | None = None,
        integrity_guard: AcademicIntegrityGuard | None = None,
    ) -> None:
        self.course_repository = course_repository
        self.conversation_repository = conversation_repository
        self.document_repository = document_repository
        self.progress_repository = progress_repository
        self.study_plan_repository = study_plan_repository
        self.practice_service = practice_service
        self.retriever = retriever or CourseRetriever()
        self.gateway = gateway or TutorAnswerGateway()
        self.intent_router = intent_router or LearningIntentRouter()
        self.tools = tools or TeachingToolManager(
            course_repository=course_repository,
            document_repository=document_repository,
            progress_repository=progress_repository,
            study_plan_repository=study_plan_repository,
            retriever=self.retriever,
            practice_service=practice_service,
            practice_repository=practice_repository,
            attempt_service=attempt_service,
            study_plan_service=study_plan_service,
        )
        self.orchestrator = orchestrator or LearningAgentOrchestrator(
            registry={
                AgentName.TUTOR: TutorAgent(self.gateway),
                AgentName.QUIZ: QuizAgent(),
                AgentName.CATALOG: CatalogAgent(),
                AgentName.PROGRESS: ProgressAgent(),
                AgentName.PLANNER: PlannerAgent(),
                AgentName.EVALUATOR: EvaluatorAgent(),
                AgentName.GENERAL: GeneralAgent(),
            },
            clarify_agent=ClarifyAgent(),
            integrity_agent=IntegrityGuardAgent(),
        )
        self.integrity_guard = integrity_guard or AcademicIntegrityGuard()

    async def _retry_with_citations(self, data, evidence, history):
        try:
            return await self.gateway.answer(
                question=data.message,
                language=data.response_language.value,
                mode=data.mode.value,
                evidence=evidence,
                history=[(item.role, item.content) for item in history],
                citation_reminder=True,
            )
        except Exception:  # noqa: BLE001 - the extractive fallback still applies
            return _extractive_answer(evidence, reason="citation_retry_failed")

    async def _material_language(self, user_id, course_id, scope) -> str:
        """The language the retrieval query has to be written in.

        Judged from the documents actually in scope, so a course holding both
        English lectures and Chinese notes still searches the right one.
        """

        documents = await self.document_repository.list_for_course(
            user_id, course_id, offset=0, limit=100
        )
        selected = set(scope.document_ids or [])
        in_scope = [item for item in documents if not selected or item.id in selected]
        languages = [getattr(item, "language", "en") or "en" for item in in_scope]
        if not languages:
            return "en"
        return max(set(languages), key=languages.count)

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

        started = monotonic()
        standalone_query = _standalone_query(data.message, history)
        effective_scope = data.scope
        learned_context = _references_learned_content(data.message)
        learned_topic = _latest_learning_request(history) if learned_context else None
        if learned_topic:
            standalone_query = f"{learned_topic}\nPractice request: {data.message}"
        if learned_context:
            learned_document_ids = _latest_cited_document_ids(history)
            if learned_document_ids:
                effective_scope = effective_scope.model_copy(
                    update={"document_ids": learned_document_ids}
                )
        if not effective_scope.document_ids and _mentions_document_reference(data.message):
            available_documents = await self.document_repository.list_for_course(
                user_id, course_id, offset=0, limit=100
            )
            resolved_ids = _resolve_document_references(data.message, available_documents)
            if resolved_ids:
                effective_scope = effective_scope.model_copy(
                    update={"document_ids": resolved_ids}
                )
                standalone_query = _document_learning_query(data.message, standalone_query)
        material_language = await self._material_language(user_id, course_id, effective_scope)
        decision = await self.intent_router.route(
            message=data.message,
            standalone_query=standalone_query,
            course_id=course_id,
            language=data.response_language.value,
            scope=effective_scope,
            history=[(item.role, item.content) for item in history],
            material_language=material_language,
        )
        context = LearningContext(
            user_id=user_id,
            course_id=course_id,
            conversation_id=conversation.id,
            message=data.message,
            language=data.response_language.value,
            mode=data.mode.value,
            scope=effective_scope,
            decision=decision,
            history=history,
            practice_options=data.practice_options,
            learned_topic=learned_topic,
            tools=self.tools,
            integrity=self.integrity_guard.evaluate(
                data.message,
                language=data.response_language.value,
                history=history,
            ),
        )
        result, trace = await self.orchestrator.run(context)
        evidence = result.evidence
        status = result.evidence_status
        practice_set = result.practice_set
        generated = GeneratedAnswer(
            answer=result.answer,
            model_name=result.model_name,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            fallback_reason=result.fallback_reason,
        )
        answer = _remove_unknown_citations(generated.answer, len(evidence))
        cited = {int(value) for value in re.findall(r"\[c(\d+)]", answer)}
        if evidence and not cited:
            # One repair attempt before giving up. Dumping raw passages loses a
            # correct answer — notably a correct "the material does not cover
            # this", which legitimately asserts nothing and so cited nothing.
            generated = await self._retry_with_citations(data, evidence, history)
            answer = _remove_unknown_citations(generated.answer, len(evidence))
            cited = {int(value) for value in re.findall(r"\[c(\d+)]", answer)}
            if not cited:
                generated = _extractive_answer(evidence, reason="citation_validation_failed")
                answer = generated.answer
                cited = {int(value) for value in re.findall(r"\[c(\d+)]", answer)}
        citations = [
            Citation(
                citation_id=f"c{index}",
                document_id=item.document_id,
                filename=item.filename,
                page_number=item.page_number,
                section_title=item.section_title,
                snippet=item.text[:CITATION_SNIPPET_LIMIT],
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
            intent=decision.intent.value,
            route=decision.target.value,
            query_plan=decision.query_plan.as_dict(),
            routing=decision.as_dict(),
            integrity=context.integrity.as_dict(),
            trace=trace.as_dict(),
            practice_set=(practice_set.model_dump(mode="json") if practice_set else None),
            fallback_reason=generated.fallback_reason,
        )


def _conversation_title(message: str) -> str:
    return " ".join(message.split())[:80]


def _mentions_document_reference(message: str) -> bool:
    normalized = message.casefold()
    ordinal_reference = re.search(
        # "资料第一章" names a chapter, not the first document, so a number
        # followed by 章/节/页 is never read as a material's ordinal.
        r"(?:资料|文件|文档|讲义|课件|pdf)\s*(?:第)?\s*(?:10|[1-9]|[一两二三四五六七八九十])(?!\s*[章节页])"
        r"|第\s*(?:10|[1-9]|[一两二三四五六七八九十])\s*(?:份|个|篇)?\s*(?:资料|文件|文档|讲义|课件|pdf)"
        r"|(?:document|file|pdf)\s*(?:#\s*)?(?:10|[1-9])",
        normalized,
        re.I,
    )
    return bool(ordinal_reference) or ".pdf" in normalized or ".md" in normalized or ".txt" in normalized


def _resolve_document_references(message: str, documents: list[Document]) -> list[UUID]:
    if not documents:
        return []
    normalized = " ".join(message.casefold().split())
    ordered = list(reversed(documents))
    matched_by_name = [
        item.id
        for item in ordered
        if item.filename.casefold() in normalized
        or _filename_stem(item.filename) in normalized
    ]
    if matched_by_name:
        return list(dict.fromkeys(matched_by_name))

    patterns = (
        r"(?:资料|文件|文档|讲义|课件|pdf)\s*(?:第)?\s*(10|[1-9]|[一两二三四五六七八九十])(?!\s*[章节页])",
        r"第\s*(10|[1-9]|[一两二三四五六七八九十])\s*(?:份|个|篇)?\s*(?:资料|文件|文档|讲义|课件|pdf)",
        r"(?:document|file|pdf)\s*(?:#\s*)?(10|[1-9])",
    )
    chinese_numbers = {
        "一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5,
        "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    }
    for pattern in patterns:
        match = re.search(pattern, normalized, re.I)
        if match:
            raw = match.group(1)
            position = int(raw) if raw.isdigit() else chinese_numbers[raw]
            return [ordered[position - 1].id] if position <= len(ordered) else []
    return []


def _filename_stem(filename: str) -> str:
    return filename.rsplit(".", 1)[0].casefold()


def _document_learning_query(message: str, standalone_query: str) -> str:
    normalized = message.casefold()
    if any(term in normalized for term in ("开始学习", "开始看", "带我学", "start studying", "study this")):
        return (
            "Identify and explain the most important concepts, prerequisite knowledge, "
            "and a sensible study sequence from the selected document."
        )
    if any(term in normalized for term in ("总结", "概括", "summary", "summarize")):
        return "Summarize the main concepts and relationships in the selected document."
    return standalone_query


def _references_learned_content(message: str) -> bool:
    normalized = " ".join(message.casefold().split())
    return any(term in normalized for term in (
        "已经学", "学过的", "刚学", "刚才学", "已学习", "学完的",
        "what i learned", "what we studied", "just studied",
    ))


def _latest_learning_request(history: list[Message]) -> str | None:
    for item in reversed(history):
        if item.role != "user":
            continue
        normalized = item.content.casefold()
        if re.search(r"(?:第\s*[一二三四五六七八九十零〇0-9]+\s*章|chapter\s*[0-9]+)", normalized, re.I):
            return item.content
    return None


def _latest_cited_document_ids(history: list[Message]) -> list[UUID]:
    for item in reversed(history):
        if item.role != "assistant" or not item.citations_json:
            continue
        values = []
        for citation in item.citations_json:
            try:
                values.append(UUID(str(citation["document_id"])))
            except (KeyError, TypeError, ValueError):
                continue
        if values:
            return list(dict.fromkeys(values))
    return []


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
        "继续",
        "接着",
        "往下",
        "举个例子",
        "what about",
        "it",
        "this",
        "that",
        "example",
        "continue",
    )
    if not any(marker in normalized for marker in followup_markers):
        return message
    previous_question = next(
        (item.content for item in reversed(history) if item.role == "user"), None
    )
    return f"{previous_question}\nFollow-up: {message}" if previous_question else message
