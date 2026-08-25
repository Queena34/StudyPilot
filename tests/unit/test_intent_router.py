from uuid import UUID

import pytest

from app.agents.intent_router import LearningIntent, LearningIntentRouter, RouteTarget
from app.schemas.tutor import TutorScope


COURSE_ID = UUID("00000000-0000-0000-0000-000000000010")


def _decision(message: str):
    return LearningIntentRouter().analyze(
        message=message,
        standalone_query=message,
        course_id=COURSE_ID,
        language="zh",
        scope=TutorScope(),
    )


@pytest.mark.parametrize(
    ("message", "intent", "target"),
    [
        ("我现在有什么课程资料？", LearningIntent.DOCUMENT_MANAGEMENT, RouteTarget.COURSE_CATALOG),
        ("我的掌握度和薄弱点怎么样？", LearningIntent.PROGRESS_REVIEW, RouteTarget.PROGRESS),
        ("我的学习计划完成了多少？", LearningIntent.STUDY_PLANNING, RouteTarget.STUDY_PLAN),
        ("给我出题测试一下", LearningIntent.PRACTICE_GENERATION, RouteTarget.PRACTICE),
        ("你好", LearningIntent.GENERAL, RouteTarget.GENERAL),
        ("请解释什么是 ANOVA", LearningIntent.CONCEPT_EXPLANATION, RouteTarget.RAG),
        ("ANOVA 的假设条件有哪些？", LearningIntent.COURSE_QA, RouteTarget.RAG),
    ],
)
def test_routes_learning_intents(message, intent, target) -> None:
    decision = _decision(message)

    assert decision.intent == intent
    assert decision.target == target


def test_query_plan_preserves_user_scope() -> None:
    document_id = UUID("00000000-0000-0000-0000-000000000020")
    decision = LearningIntentRouter().analyze(
        message="解释正则化",
        standalone_query="Explain regularization",
        course_id=COURSE_ID,
        language="zh-en",
        scope=TutorScope(document_ids=[document_id], page_from=2, page_to=5),
    )

    assert decision.query_plan.document_ids == [document_id]
    assert decision.query_plan.page_from == 2
    assert decision.query_plan.page_to == 5
    assert decision.query_plan.requested_language == "zh-en"
