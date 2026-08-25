import re
from time import monotonic
from uuid import UUID, uuid4

from app.agents.intent_router import LearningIntentRouter, RouteTarget
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


class TutorService:
    def __init__(
        self,
        course_repository: CourseRepository,
        conversation_repository: ConversationRepository,
        document_repository: DocumentRepository,
        progress_repository: ProgressRepository,
        study_plan_repository: StudyPlanRepository,
        retriever: CourseRetriever | None = None,
        gateway: TutorAnswerGateway | None = None,
        intent_router: LearningIntentRouter | None = None,
    ) -> None:
        self.course_repository = course_repository
        self.conversation_repository = conversation_repository
        self.document_repository = document_repository
        self.progress_repository = progress_repository
        self.study_plan_repository = study_plan_repository
        self.retriever = retriever or CourseRetriever()
        self.gateway = gateway or TutorAnswerGateway()
        self.intent_router = intent_router or LearningIntentRouter()

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
        decision = self.intent_router.analyze(
            message=data.message,
            standalone_query=standalone_query,
            course_id=course_id,
            language=data.response_language.value,
            scope=data.scope,
        )
        if decision.target == RouteTarget.COURSE_CATALOG:
            documents = await self.document_repository.list_for_course(
                user_id, course_id, offset=0, limit=100
            )
            evidence = []
            status = "catalog"
            generated = GeneratedAnswer(
                answer=_document_inventory_answer(documents, data.response_language.value),
                model_name="course-catalog",
            )
        elif decision.target == RouteTarget.PROGRESS:
            topics = await self.progress_repository.list_topics(user_id, course_id)
            total_attempts = await self.progress_repository.count_attempts(user_id, course_id)
            evidence = []
            status = "business_data"
            generated = GeneratedAnswer(
                answer=_progress_answer(topics, total_attempts, data.response_language.value),
                model_name="progress-service",
            )
        elif decision.target == RouteTarget.STUDY_PLAN:
            plans = await self.study_plan_repository.list_for_course(
                user_id, course_id, offset=0, limit=5
            )
            evidence = []
            status = "business_data"
            generated = GeneratedAnswer(
                answer=_study_plan_answer(plans, data.response_language.value),
                model_name="study-plan-service",
            )
        elif decision.target == RouteTarget.PRACTICE:
            evidence = []
            status = "action_required"
            generated = GeneratedAnswer(
                answer=_practice_route_answer(data.response_language.value),
                model_name="practice-router",
            )
        elif decision.target == RouteTarget.GENERAL:
            evidence = []
            status = "general"
            generated = GeneratedAnswer(
                answer=_general_answer(data.response_language.value),
                model_name="general-router",
            )
        else:
            scope = data.scope
            evidence = await self.retriever.retrieve(
                user_id=user_id,
                course_id=course_id,
                query=decision.query_plan.standalone_query,
                top_k=decision.query_plan.top_k,
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
            intent=decision.intent.value,
            route=decision.target.value,
            query_plan=decision.query_plan.as_dict(),
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
    if status == "catalog":
        return ["请概括这些资料的主题。", "这些资料有哪些共同知识点？"]
    if status == "business_data":
        return ["我下一步应该学什么？", "帮我安排一份复习计划。"]
    if status == "action_required":
        return ["我想练习薄弱知识点。", "请先解释一个核心概念。"]
    if status == "general":
        return ["我现在有哪些课程资料？", "帮我解释一个课程概念。"]
    if status == "insufficient":
        return ["要不要换一个关键词提问？", "是否需要上传更多课程资料？"]
    return ["能否用一个具体例子说明？", "请根据这些内容出一道练习题。"]


def _conversation_title(message: str) -> str:
    return " ".join(message.split())[:80]


def _document_inventory_answer(documents: list[Document], language: str) -> str:
    if not documents:
        if language == "en":
            return "There are no course materials in this course yet."
        return "这门课目前还没有上传课程资料。"

    status_zh = {
        "ready": "已就绪",
        "queued": "等待处理",
        "processing": "正在处理",
        "failed": "处理失败",
        "uploaded": "已上传",
    }
    status_en = {
        "ready": "ready",
        "queued": "queued",
        "processing": "processing",
        "failed": "failed",
        "uploaded": "uploaded",
    }
    if language == "en":
        lines = [f"This course currently has {len(documents)} material(s):"]
        for index, document in enumerate(reversed(documents), start=1):
            details = [status_en.get(document.status, document.status)]
            if document.page_count:
                details.append(f"{document.page_count} pages")
            if document.chunk_count:
                details.append(f"{document.chunk_count} knowledge chunks")
            lines.append(f"{index}. {document.filename} ({', '.join(details)})")
        return "\n".join(lines)

    lines = [f"这门课目前共有 {len(documents)} 份课程资料："]
    for index, document in enumerate(reversed(documents), start=1):
        details = [status_zh.get(document.status, document.status)]
        if document.page_count:
            details.append(f"{document.page_count} 页")
        if document.chunk_count:
            details.append(f"{document.chunk_count} 个知识片段")
        lines.append(f"{index}. {document.filename}（{'、'.join(details)}）")
    return "\n".join(lines)


def _progress_answer(topics: list, total_attempts: int, language: str) -> str:
    if not topics:
        if language == "en":
            return "You have not completed any graded practice yet, so mastery data is unavailable."
        return "你还没有完成已批改的练习，目前还无法计算知识点掌握度。"
    overall = sum(item.mastery_score for item in topics) / len(topics)
    weakest = sorted(topics, key=lambda item: item.mastery_score)[:3]
    if language == "en":
        names = ", ".join(f"{item.display_topic} ({item.mastery_score:.0%})" for item in weakest)
        return f"Overall mastery: {overall:.0%} from {total_attempts} attempts. Focus next on: {names}."
    names = "、".join(f"{item.display_topic}（{item.mastery_score:.0%}）" for item in weakest)
    return f"你目前的总体掌握度约为 {overall:.0%}，已完成 {total_attempts} 次作答。建议优先加强：{names}。"


def _study_plan_answer(plans: list, language: str) -> str:
    if not plans:
        if language == "en":
            return "There is no study plan for this course yet. Create one in the Study Plan tab."
        return "这门课还没有学习计划。你可以在“学习计划”中设置天数和每日时间后生成。"
    plan = plans[0]
    completed = sum(task.status == "completed" for task in plan.tasks)
    total = len(plan.tasks)
    completion_rate = completed / max(1, total)
    pending = next((task for task in plan.tasks if task.status != "completed"), None)
    if language == "en":
        next_text = f" Next: {pending.title}." if pending else " All tasks are complete."
        return f"Your latest plan is {completed}/{total} tasks complete ({completion_rate:.0%}).{next_text}"
    next_text = f"下一项：{pending.title}。" if pending else "所有任务都已完成。"
    return f"你最新的学习计划已完成 {completed}/{total} 项（{completion_rate:.0%}）。{next_text}"


def _practice_route_answer(language: str) -> str:
    if language == "en":
        return "I recognized a practice-generation request. Open Practice Quiz to choose the topic, question type, difficulty, and count so the questions and grading rubric are saved correctly."
    return "我已识别到你想生成练习。请打开“练习自测”，选择主题、题型、难度和数量，这样系统会正确保存题目和批改标准。"


def _general_answer(language: str) -> str:
    if language == "en":
        return "I am your StudyPilot coach. I can explain uploaded materials with citations, review progress, show study plans, and help you create targeted practice."
    return "我是你的 StudyPilot 学习教练。我可以基于课程资料带引用讲解知识、查看学习进度和计划，也可以帮你进行针对性练习。"


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
