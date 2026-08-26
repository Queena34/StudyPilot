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
        retriever: CourseRetriever | None = None,
        gateway: TutorAnswerGateway | None = None,
        intent_router: LearningIntentRouter | None = None,
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
        practice_set = None
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
        decision = await self.intent_router.route(
            message=data.message,
            standalone_query=standalone_query,
            course_id=course_id,
            language=data.response_language.value,
            scope=effective_scope,
            history=[(item.role, item.content) for item in history],
        )
        if decision.target == RouteTarget.CLARIFY:
            evidence = []
            status = "clarification"
            generated = GeneratedAnswer(
                answer=decision.clarification or _general_answer(data.response_language.value),
                model_name="intent-router",
            )
        elif decision.target == RouteTarget.COURSE_CATALOG:
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
            configuration = _practice_configuration(
                data.message,
                data.response_language,
                effective_scope,
                options=data.practice_options,
                context_topic=learned_topic,
            )
            practice_set = await self.practice_service.create(
                user_id, course_id, configuration
            )
            evidence = []
            status = "practice_created"
            generated = GeneratedAnswer(
                answer=_practice_created_answer(practice_set, data.response_language.value),
                model_name=practice_set.model_name,
            )
        elif decision.target == RouteTarget.GENERAL:
            evidence = []
            status = "general"
            generated = GeneratedAnswer(
                answer=_general_answer(data.response_language.value),
                model_name="general-router",
            )
        else:
            evidence = await self.retriever.retrieve(
                user_id=user_id,
                course_id=course_id,
                query=decision.query_plan.standalone_query,
                top_k=decision.query_plan.top_k,
                document_types=decision.query_plan.document_types or None,
                document_ids=decision.query_plan.document_ids or None,
                page_from=decision.query_plan.page_from,
                page_to=decision.query_plan.page_to,
            )
            status = _evidence_status(evidence)
            if evidence:
                generated = await self.gateway.answer(
                    question=data.message,
                    language=data.response_language.value,
                    mode=data.mode.value,
                    evidence=evidence,
                    history=[(item.role, item.content) for item in history],
                )
            else:
                generated = _extractive_answer(evidence, reason="insufficient_evidence")
        answer = _remove_unknown_citations(generated.answer, len(evidence))
        cited = {int(value) for value in re.findall(r"\[c(\d+)]", answer)}
        if evidence and not cited:
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
            routing=decision.as_dict(),
            practice_set=(practice_set.model_dump(mode="json") if practice_set else None),
            fallback_reason=generated.fallback_reason,
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
    if status == "practice_created":
        return ["批改后解释我的错误。", "再生成一组更难的题。"]
    if status == "general":
        return ["我现在有哪些课程资料？", "帮我解释一个课程概念。"]
    if status == "insufficient":
        return ["要不要换一个关键词提问？", "是否需要上传更多课程资料？"]
    return ["能否用一个具体例子说明？", "请根据这些内容出一道练习题。"]


def _conversation_title(message: str) -> str:
    return " ".join(message.split())[:80]


def _mentions_document_reference(message: str) -> bool:
    normalized = message.casefold()
    ordinal_reference = re.search(
        r"(?:资料|文件|文档|讲义|课件|pdf)\s*(?:第)?\s*(?:10|[1-9]|[一两二三四五六七八九十])"
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
        r"(?:资料|文件|文档|讲义|课件|pdf)\s*(?:第)?\s*(10|[1-9]|[一两二三四五六七八九十])",
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


def _practice_configuration(
    message: str, language, scope, *, options=None, context_topic: str | None = None
) -> PracticeSetCreate:
    normalized = " ".join(message.casefold().split())
    number_match = re.search(r"(10|[1-9])\s*(?:道|题|questions?)", normalized)
    chinese_numbers = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    chinese_match = re.search(r"([一两二三四五六七八九十])\s*道", normalized)
    default_count = options.question_count if options else 3
    count = int(number_match.group(1)) if number_match else (
        chinese_numbers[chinese_match.group(1)] if chinese_match else default_count
    )
    if any(term in normalized for term in ("选择题", "单选", "multiple choice")):
        question_type = QuestionType.SINGLE_CHOICE
    elif any(term in normalized for term in ("概念题", "概念解释", "concept question")):
        question_type = QuestionType.CONCEPT
    elif any(term in normalized for term in ("简答题", "问答题", "short answer")):
        question_type = QuestionType.SHORT_ANSWER
    else:
        question_type = QuestionType(options.question_type) if options else QuestionType.SHORT_ANSWER
    if any(term in normalized for term in ("基础", "简单", "basic", "easy")):
        difficulty = Difficulty.BASIC
    elif any(term in normalized for term in ("困难", "挑战", "高级", "advanced", "hard")):
        difficulty = Difficulty.ADVANCED
    else:
        difficulty = Difficulty(options.difficulty) if options else Difficulty.MEDIUM
    topic_match = re.search(r"(?:关于|针对|topic[:：]?)\s*([^,，。.!?？]{2,80})", message, re.I)
    topic = context_topic or (topic_match.group(1).strip() if topic_match else None)
    return PracticeSetCreate(
        topic=topic,
        question_type=question_type,
        difficulty=difficulty,
        question_count=count,
        language=language,
        prioritize_weak_topics=any(term in normalized for term in ("薄弱", "弱项", "weak")),
        scope=scope,
    )


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


def _practice_created_answer(practice_set, language: str) -> str:
    count = len(practice_set.questions)
    if language == "en":
        return f'I created and saved "{practice_set.title}" with {count} question(s). Answer them below for grading.'
    return f"已为你生成并保存“{practice_set.title}”，共 {count} 道题。请直接在下方作答，提交后会自动批改。"


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
