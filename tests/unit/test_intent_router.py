from uuid import UUID

import pytest

from app.agents.intent_router import (
    AgentName,
    ExecutionMode,
    LearningIntent,
    LearningIntentRouter,
    RouteTarget,
    RoutingSource,
)
from app.agents.llm_router import LLMRoutingProposal
from app.agents.routing import RULE_CONFIDENCE_THRESHOLD
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
        ("给我出3道基础选择题", LearningIntent.PRACTICE_GENERATION, RouteTarget.PRACTICE),
        ("你好", LearningIntent.GENERAL, RouteTarget.GENERAL),
        ("请解释什么是 ANOVA", LearningIntent.CONCEPT_EXPLANATION, RouteTarget.RAG),
        ("ANOVA 的假设条件有哪些？", LearningIntent.COURSE_QA, RouteTarget.RAG),
        (
            "根据资料第一章，什么是残差，它和误差有什么区别？",
            LearningIntent.CONCEPT_EXPLANATION,
            RouteTarget.RAG,
        ),
        (
            "指定 ANOVA 资料列出的基本假设有哪些？",
            LearningIntent.COURSE_QA,
            RouteTarget.RAG,
        ),
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


class _StubLLMRouter:
    """Records what the hybrid router sends to the model and returns a fixed proposal."""

    def __init__(self, proposal: LLMRoutingProposal | None) -> None:
        self.proposal = proposal
        self.calls: list[dict] = []

    async def propose(self, *, message, history=None):
        self.calls.append({"message": message, "history": history})
        return self.proposal


async def _route(message: str, llm_router, *, scope: TutorScope | None = None):
    return await LearningIntentRouter(llm_router=llm_router).route(
        message=message,
        standalone_query=message,
        course_id=COURSE_ID,
        language="zh",
        scope=scope or TutorScope(),
    )


@pytest.mark.asyncio
async def test_high_confidence_rules_skip_the_llm_router() -> None:
    stub = _StubLLMRouter(None)

    decision = await _route("我现在有什么课程资料？", stub)

    assert decision.source == RoutingSource.RULE
    assert decision.confidence >= RULE_CONFIDENCE_THRESHOLD
    assert stub.calls == []


@pytest.mark.asyncio
async def test_composite_message_falls_back_to_the_llm_router() -> None:
    stub = _StubLLMRouter(
        LLMRoutingProposal(
            intent=LearningIntent.CONCEPT_EXPLANATION,
            supporting_agents=[AgentName.QUIZ],
            confidence=0.86,
            reason="Explain first, then generate practice.",
        )
    )

    decision = await _route("讲解一下第二章，然后给我出5道题", stub)

    assert len(stub.calls) == 1
    assert decision.source == RoutingSource.LLM
    assert decision.intent == LearningIntent.CONCEPT_EXPLANATION
    assert decision.primary_agent == AgentName.TUTOR
    assert decision.supporting_agents == [AgentName.QUIZ]
    assert decision.execution_mode == ExecutionMode.SEQUENTIAL
    assert decision.rule_confidence is not None


@pytest.mark.asyncio
async def test_unavailable_llm_router_keeps_the_rule_decision() -> None:
    decision = await _route("嗯这个", _StubLLMRouter(None))

    assert decision.source == RoutingSource.LLM_UNAVAILABLE
    assert decision.intent == LearningIntent.COURSE_QA
    assert decision.target == RouteTarget.RAG


@pytest.mark.asyncio
async def test_less_confident_llm_proposal_is_rejected() -> None:
    stub = _StubLLMRouter(
        LLMRoutingProposal(intent=LearningIntent.GENERAL, confidence=0.10, reason="unsure")
    )

    decision = await _route("嗯这个", stub)

    assert decision.source == RoutingSource.LLM_REJECTED
    assert decision.intent == LearningIntent.COURSE_QA


@pytest.mark.asyncio
async def test_low_confidence_routing_asks_for_clarification() -> None:
    stub = _StubLLMRouter(
        LLMRoutingProposal(
            intent=LearningIntent.STUDY_PLANNING, confidence=0.42, reason="ambiguous"
        )
    )

    decision = await _route("那个东西", stub)

    assert decision.target == RouteTarget.CLARIFY
    assert decision.execution_mode == ExecutionMode.CLARIFY
    assert decision.clarification


@pytest.mark.asyncio
async def test_llm_router_never_widens_explicit_learner_scope() -> None:
    document_id = UUID("00000000-0000-0000-0000-000000000020")
    stub = _StubLLMRouter(
        LLMRoutingProposal(
            intent=LearningIntent.COURSE_QA,
            confidence=0.90,
            reason="grounded question",
            standalone_query="a rewritten retrieval query",
        )
    )
    scope = TutorScope(document_ids=[document_id], page_from=2, page_to=5)

    decision = await _route("那个东西", stub, scope=scope)

    assert decision.query_plan.document_ids == [document_id]
    assert decision.query_plan.page_from == 2
    assert decision.query_plan.page_to == 5
    assert decision.query_plan.course_id == COURSE_ID
    # The message is never accompanied by the learner's scope, so the model cannot echo it back.
    assert "00000000-0000-0000-0000-000000000020" not in stub.calls[0]["message"]


def test_routing_decision_serializes_the_full_contract() -> None:
    payload = _decision("我现在有什么课程资料？").as_dict()

    assert set(payload) >= {
        "intent",
        "primary_agent",
        "supporting_agents",
        "execution_mode",
        "confidence",
        "reason",
        "source",
        "target",
        "query_plan",
    }
