"""Hybrid learning intent router: deterministic rules first, LLM only when unsure.

Deterministic rules own the high-frequency, unambiguous requests. The structured
LLM router in `app.agents.llm_router` is consulted only for low-confidence,
ambiguous or composite messages. The learner's explicit course and material scope
is copied straight from `TutorScope` and is never exposed to the model, so no
routing path can widen or replace it.
"""

from dataclasses import replace
import re
from uuid import UUID

from app.agents.llm_router import LLMIntentRouter, LLMRoutingProposal
from app.agents.query_translation import QueryTranslationGateway
from app.agents.routing import (
    CLARIFICATION_THRESHOLD,
    INTENT_AGENTS,
    INTENT_TARGETS,
    RULE_CONFIDENCE_THRESHOLD,
    AgentName,
    ExecutionMode,
    LearningIntent,
    QueryPlan,
    RouteTarget,
    RoutingDecision,
    RoutingSource,
    decision_for,
)
from app.rag.retrieval import _chapter_number
from app.schemas.tutor import TutorScope

# Re-exported so existing importers keep working after the protocol move.
__all__ = [
    "AgentName",
    "ExecutionMode",
    "LearningIntent",
    "LearningIntentRouter",
    "QueryPlan",
    "RouteTarget",
    "RoutingDecision",
    "RoutingSource",
]

# Backwards-compatible alias for the pre-hybrid return type.
IntentDecision = RoutingDecision


class LearningIntentRouter:
    """Rule-first router with a structured LLM fallback for unclear messages."""

    def __init__(
        self,
        llm_router: LLMIntentRouter | None = None,
        translator: QueryTranslationGateway | None = None,
    ) -> None:
        self.llm_router = llm_router or LLMIntentRouter()
        self.translator = translator or QueryTranslationGateway()

    def analyze(
        self,
        *,
        message: str,
        standalone_query: str,
        course_id: UUID,
        language: str,
        scope: TutorScope,
    ) -> RoutingDecision:
        """Deterministic-only routing. Kept synchronous for callers that cannot await."""

        plan = _build_plan(message, standalone_query, course_id, language, scope)
        return _rule_decision(message, plan)

    async def route(
        self,
        *,
        message: str,
        standalone_query: str,
        course_id: UUID,
        language: str,
        scope: TutorScope,
        history: list[tuple[str, str]] | None = None,
        material_language: str = "en",
    ) -> RoutingDecision:
        """Full hybrid routing. Falls back to the rule decision on any LLM problem."""

        plan = _build_plan(
            message, standalone_query, course_id, language, scope, material_language
        )
        plan = replace(
            plan,
            retrieval_query=await self.translator.to_material_language(
                plan.standalone_query, material_language
            ),
        )
        rule = _rule_decision(message, plan, has_history=bool(history))
        if rule.confidence >= RULE_CONFIDENCE_THRESHOLD:
            return rule

        proposal = await self.llm_router.propose(message=message, history=history)
        if proposal is None:
            return _mark_unresolved(rule, RoutingSource.LLM_UNAVAILABLE)
        if proposal.confidence < rule.confidence:
            return _mark_unresolved(rule, RoutingSource.LLM_REJECTED)
        return _merge(rule, proposal, plan, message, standalone_query)


def _build_plan(
    message: str,
    standalone_query: str,
    course_id: UUID,
    language: str,
    scope: TutorScope,
    material_language: str = "en",
) -> QueryPlan:
    """Scope comes only from the learner's explicit selection, never from a model."""

    return QueryPlan(
        standalone_query=standalone_query,
        course_id=course_id,
        document_types=[item.value for item in scope.document_types],
        document_ids=scope.document_ids,
        page_from=scope.page_from,
        page_to=scope.page_to,
        # An explicit choice always wins; otherwise read the chapter the learner
        # named. This is the one place a chapter is derived from a message.
        requested_language=language,
        top_k=8,
        # An explicit choice always wins; otherwise read the chapter the learner
        # named. This is the one place a chapter is derived from a message.
        chapter=scope.chapter if scope.chapter is not None else _resolve_chapter(message),
        material_language=material_language,
    )


def _merge(
    rule: RoutingDecision,
    proposal: LLMRoutingProposal,
    plan: QueryPlan,
    message: str,
    standalone_query: str,
) -> RoutingDecision:
    intent = proposal.intent
    supporting = [
        agent for agent in proposal.supporting_agents if agent != INTENT_AGENTS[intent]
    ]
    merged_plan = plan
    if (
        proposal.standalone_query
        and INTENT_TARGETS[intent] == RouteTarget.RAG
        and standalone_query.strip() == message.strip()
    ):
        # Only refine the query when nothing upstream already enriched it.
        merged_plan = QueryPlan(
            standalone_query=proposal.standalone_query.strip()[:1000],
            course_id=plan.course_id,
            document_types=plan.document_types,
            document_ids=plan.document_ids,
            page_from=plan.page_from,
            page_to=plan.page_to,
            requested_language=plan.requested_language,
            top_k=plan.top_k,
        )

    decision = decision_for(
        intent,
        confidence=proposal.confidence,
        reason=proposal.reason.strip()[:300] or "LLM router classified an unclear message.",
        query_plan=merged_plan,
        source=RoutingSource.LLM,
        supporting_agents=supporting,
        rule_confidence=rule.confidence,
    )
    if proposal.confidence < CLARIFICATION_THRESHOLD:
        return _as_clarification(decision)
    return decision


def _mark_unresolved(rule: RoutingDecision, source: RoutingSource) -> RoutingDecision:
    """Keep the deterministic result but record why the LLM stage did not apply."""

    return replace(rule, source=source, rule_confidence=rule.confidence)


def _as_clarification(decision: RoutingDecision) -> RoutingDecision:
    return replace(
        decision,
        target=RouteTarget.CLARIFY,
        execution_mode=ExecutionMode.CLARIFY,
        clarification=(
            "我不确定你想要课程讲解、生成练习、查看进度还是学习计划，能再说得具体一点吗？"
        ),
    )


def _resolve_chapter(message: str) -> int | None:
    """Read a chapter the learner named. Delegates the parsing to the retriever's
    own chapter reader so the two can never disagree about what "第一章" means."""

    return _chapter_number(message)


def _rule_decision(
    message: str, plan: QueryPlan, *, has_history: bool = False
) -> RoutingDecision:
    normalized = " ".join(message.casefold().split())
    matches = _rule_matches(normalized)

    if has_history and _is_context_dependent(normalized):
        # A follow-up that leans on earlier turns is exactly the low-confidence
        # case the LLM stage exists for, unless an explicit operation was named.
        if not matches or matches[0][1] < _EXPLICIT_OPERATION_CONFIDENCE:
            intent = matches[0][0] if matches else LearningIntent.COURSE_QA
            return decision_for(
                intent,
                confidence=0.55,
                reason="The message depends on earlier turns and names no explicit operation.",
                query_plan=plan,
            )

    if len(matches) > 1:
        return decision_for(
            matches[0][0],
            confidence=0.50,
            reason="The message matched more than one learning intent; it may be composite.",
            query_plan=plan,
        )
    if matches:
        intent, confidence, reason = matches[0]
        return decision_for(intent, confidence=confidence, reason=reason, query_plan=plan)
    if _is_question(normalized):
        return decision_for(
            LearningIntent.COURSE_QA,
            confidence=0.85,
            reason="The message is phrased as a question about the course material.",
            query_plan=plan,
        )
    return decision_for(
        LearningIntent.COURSE_QA,
        confidence=0.40,
        reason="No rule matched and the message is not phrased as a question.",
        query_plan=plan,
    )


def _rule_matches(message: str) -> list[tuple[LearningIntent, float, str]]:
    """All deterministic matches, most specific first."""

    matches: list[tuple[LearningIntent, float, str]] = []
    if _is_catalog_request(message):
        matches.append((
            LearningIntent.DOCUMENT_MANAGEMENT,
            0.99,
            "The user asked for course-material metadata, not document content.",
        ))
    if _contains(message, _PROGRESS_TERMS):
        matches.append((
            LearningIntent.PROGRESS_REVIEW,
            0.95,
            "The user asked about mastery, weak topics, or learning progress.",
        ))
    if _contains(message, _PLAN_TERMS):
        matches.append((
            LearningIntent.STUDY_PLANNING,
            0.93,
            "The user asked about a study or revision plan.",
        ))
    if _is_answer_submission(message):
        matches.append((
            LearningIntent.ANSWER_EVALUATION,
            0.96,
            "The user submitted an answer for grading.",
        ))
    if _is_practice_request(message):
        matches.append((
            LearningIntent.PRACTICE_GENERATION,
            0.94,
            "The user asked to generate questions or start a quiz.",
        ))
    if _is_general(message):
        matches.append((
            LearningIntent.GENERAL,
            0.98,
            "The message is a greeting or a request for product capabilities.",
        ))
    if _contains(message, _EXPLANATION_TERMS):
        matches.append((
            LearningIntent.CONCEPT_EXPLANATION,
            0.88,
            "The user asked for a course concept explanation.",
        ))
    return matches


def _contains(message: str, terms: tuple[str, ...]) -> bool:
    return any(term in message for term in terms)


def _is_question(message: str) -> bool:
    if message.rstrip().endswith(("?", "？")):
        return True
    if _contains(message, _QUESTION_TERMS):
        return True
    return bool(re.match(r"^(?:what|why|how|when|where|which|who|is|are|does|do|can)\b", message))


def _is_general(message: str) -> bool:
    exact = {"你好", "嗨", "hello", "hi", "hey", "你是谁", "who are you"}
    return message.strip("！!?？。. ") in exact or _contains(message, _CAPABILITY_TERMS)


def _is_practice_request(message: str) -> bool:
    return _contains(message, _PRACTICE_TERMS) or bool(
        re.search(r"(?:出|生成|创建).{0,12}(?:题|练习|测验)", message)
    )


def _is_answer_submission(message: str) -> bool:
    """Only explicit submissions, so ordinary questions are never graded by mistake."""

    return bool(
        # "我答" must introduce an answer, not appear inside "给我答案".
        re.search(r"(?:我的答案|我的回答)\s*(?:是|为)?\s*[：:]?\s*\S", message)
        or re.search(r"(?:^|[，,。.；;\s])(?:我答|我选)\s*(?:是|为)?\s*[：:]?\s*\S", message)
        or re.search(r"^(?:答案|answer)\s*[：:]\s*\S", message)
        or _contains(message, _SUBMISSION_TERMS)
    )


def _is_catalog_request(message: str) -> bool:
    """Match inventory requests without confusing questions about document content."""
    document = r"(?:课程资料|资料|文件|文档|讲义|课件)"
    before_document = r"(?:有什么|有哪些|哪几份|几份|上传了什么|上传过哪些)"
    after_document = r"(?:有什么|有哪些|哪几份|几份|清单|列表)"
    english = (
        "what do i have",
        "what materials",
        "which document",
        "list documents",
        "list files",
        "uploaded files",
    )
    return bool(
        re.search(rf"{before_document}.{{0,4}}{document}", message)
        or re.search(rf"{document}.{{0,2}}{after_document}(?:[？?。. ]*)$", message)
        or re.search(rf"(?:查看|显示|列出).{{0,4}}{document}(?:清单|列表)?", message)
        or _contains(message, english)
    )


_PROGRESS_TERMS = (
    "学习进度", "掌握度", "掌握得", "薄弱", "弱项", "学得怎么样",
    "progress", "mastery", "weak topic", "weakness",
)
_PLAN_TERMS = (
    "学习计划", "复习计划", "复习安排", "学习安排", "备考计划",
    "study plan", "revision plan", "study schedule",
)
_PRACTICE_TERMS = (
    "给我出题", "出几道题", "生成练习", "开始练习", "测试我", "自测",
    "generate questions", "create a quiz", "quiz me", "practice questions",
)
_SUBMISSION_TERMS = (
    "帮我批改", "帮我改一下", "看看我答得对不对", "评一下我的答案", "给我打分",
    "grade my answer", "check my answer", "mark my answer", "how did i do on",
)
_CAPABILITY_TERMS = (
    "你能做什么", "怎么用", "使用帮助", "what can you do", "how to use",
)
_EXPLANATION_TERMS = (
    "解释", "讲解", "什么是", "为什么", "举个例子", "区别",
    "explain", "what is", "why", "example", "difference between",
)
#: Rules at or above this confidence name an explicit operation and are trusted
#: even in a follow-up turn.
_EXPLICIT_OPERATION_CONFIDENCE = 0.90


def _is_context_dependent(message: str) -> bool:
    return _contains(message, _ANAPHORA_TERMS) or len(message.strip("！!?？。. ")) <= 6


_ANAPHORA_TERMS = (
    "那个", "那这", "那我", "这个", "它", "再来", "再详细", "再多",
    "继续", "换成", "接下来", "还有呢", "刚才", "上面",
    "that one", "it again", "more of", "keep going", "same thing",
)
_QUESTION_TERMS = (
    "吗", "呢", "怎么", "如何", "哪些", "哪个", "多少", "是否", "什么",
    "为什么", "能不能", "可不可以",
)
