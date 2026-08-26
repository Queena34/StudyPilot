from dataclasses import dataclass
from enum import Enum
import re
from uuid import UUID

from app.schemas.tutor import TutorScope


class LearningIntent(str, Enum):
    COURSE_QA = "course_qa"
    CONCEPT_EXPLANATION = "concept_explanation"
    PRACTICE_GENERATION = "practice_generation"
    ANSWER_EVALUATION = "answer_evaluation"
    STUDY_PLANNING = "study_planning"
    PROGRESS_REVIEW = "progress_review"
    DOCUMENT_MANAGEMENT = "document_management"
    GENERAL = "general"


class RouteTarget(str, Enum):
    RAG = "rag"
    COURSE_CATALOG = "course_catalog"
    PROGRESS = "progress"
    STUDY_PLAN = "study_plan"
    PRACTICE = "practice"
    GENERAL = "general"


@dataclass(frozen=True)
class QueryPlan:
    standalone_query: str
    course_id: UUID
    document_types: list[str]
    document_ids: list[UUID]
    page_from: int | None
    page_to: int | None
    requested_language: str
    top_k: int

    def as_dict(self) -> dict:
        return {
            "standalone_query": self.standalone_query,
            "course_id": str(self.course_id),
            "document_types": self.document_types,
            "document_ids": [str(value) for value in self.document_ids],
            "page_from": self.page_from,
            "page_to": self.page_to,
            "requested_language": self.requested_language,
            "top_k": self.top_k,
        }


@dataclass(frozen=True)
class IntentDecision:
    intent: LearningIntent
    target: RouteTarget
    confidence: float
    reason: str
    query_plan: QueryPlan


class LearningIntentRouter:
    """High-precision deterministic router for the MVP unified chat entry."""

    def analyze(
        self,
        *,
        message: str,
        standalone_query: str,
        course_id: UUID,
        language: str,
        scope: TutorScope,
    ) -> IntentDecision:
        normalized = " ".join(message.casefold().split())
        plan = QueryPlan(
            standalone_query=standalone_query,
            course_id=course_id,
            document_types=[item.value for item in scope.document_types],
            document_ids=scope.document_ids,
            page_from=scope.page_from,
            page_to=scope.page_to,
            requested_language=language,
            top_k=8,
        )

        if _is_catalog_request(normalized):
            return IntentDecision(
                LearningIntent.DOCUMENT_MANAGEMENT,
                RouteTarget.COURSE_CATALOG,
                0.99,
                "The user asked for course-material metadata, not document content.",
                plan,
            )
        if _contains(normalized, _PROGRESS_TERMS):
            return IntentDecision(
                LearningIntent.PROGRESS_REVIEW,
                RouteTarget.PROGRESS,
                0.95,
                "The user asked about mastery, weak topics, or learning progress.",
                plan,
            )
        if _contains(normalized, _PLAN_TERMS):
            return IntentDecision(
                LearningIntent.STUDY_PLANNING,
                RouteTarget.STUDY_PLAN,
                0.93,
                "The user asked about a study or revision plan.",
                plan,
            )
        if _is_practice_request(normalized):
            return IntentDecision(
                LearningIntent.PRACTICE_GENERATION,
                RouteTarget.PRACTICE,
                0.94,
                "The user asked to generate questions or start a quiz.",
                plan,
            )
        if _is_general(normalized):
            return IntentDecision(
                LearningIntent.GENERAL,
                RouteTarget.GENERAL,
                0.98,
                "The message is a greeting or a request for product capabilities.",
                plan,
            )
        if _contains(normalized, _EXPLANATION_TERMS):
            return IntentDecision(
                LearningIntent.CONCEPT_EXPLANATION,
                RouteTarget.RAG,
                0.88,
                "The user asked for a course concept explanation.",
                plan,
            )
        return IntentDecision(
            LearningIntent.COURSE_QA,
            RouteTarget.RAG,
            0.65,
            "No high-confidence operational intent matched; use grounded course Q&A.",
            plan,
        )


def _contains(message: str, terms: tuple[str, ...]) -> bool:
    return any(term in message for term in terms)


def _is_general(message: str) -> bool:
    exact = {"你好", "嗨", "hello", "hi", "hey", "你是谁", "who are you"}
    return message.strip("！!?？。. ") in exact or _contains(message, _CAPABILITY_TERMS)


def _is_practice_request(message: str) -> bool:
    return _contains(message, _PRACTICE_TERMS) or bool(
        re.search(r"(?:出|生成|创建).{0,12}(?:题|练习|测验)", message)
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
_CAPABILITY_TERMS = (
    "你能做什么", "怎么用", "使用帮助", "what can you do", "how to use",
)
_EXPLANATION_TERMS = (
    "解释", "讲解", "什么是", "为什么", "举个例子", "区别",
    "explain", "what is", "why", "example", "difference between",
)
