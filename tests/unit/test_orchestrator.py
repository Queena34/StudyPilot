from uuid import UUID, uuid4

import pytest

from app.agents.learning_agents import ClarifyAgent
from app.agents.orchestrator import LearningAgentOrchestrator
from app.agents.protocol import (
    AgentResult,
    AgentStatus,
    AgentTask,
    LearningContext,
    ToolCall,
)
from app.agents.routing import (
    AgentName,
    ExecutionMode,
    LearningIntent,
    QueryPlan,
    RouteTarget,
    RoutingDecision,
    decision_for,
)
from app.schemas.tutor import TutorScope


COURSE_ID = UUID("00000000-0000-0000-0000-000000000010")
USER_ID = UUID("00000000-0000-0000-0000-000000000011")


class _RecordingAgent:
    def __init__(self, name: AgentName, result: AgentResult) -> None:
        self.name = name
        self.result = result
        self.tasks: list[AgentTask] = []

    async def run(self, task: AgentTask, context: LearningContext) -> AgentResult:
        self.tasks.append(task)
        return self.result


class _FailingAgent:
    def __init__(self, name: AgentName) -> None:
        self.name = name

    async def run(self, task: AgentTask, context: LearningContext) -> AgentResult:
        raise RuntimeError("practice service is down")


def _plan() -> QueryPlan:
    return QueryPlan(
        standalone_query="what is a residual",
        course_id=COURSE_ID,
        document_types=[],
        document_ids=[],
        page_from=None,
        page_to=None,
        requested_language="zh",
        top_k=8,
    )


def _context(decision: RoutingDecision) -> LearningContext:
    return LearningContext(
        user_id=USER_ID,
        course_id=COURSE_ID,
        conversation_id=uuid4(),
        message="讲解残差，然后出3道题",
        language="zh",
        mode="standard",
        scope=TutorScope(),
        decision=decision,
    )


def _sequential(primary: LearningIntent, supporting: list[AgentName]) -> RoutingDecision:
    return decision_for(
        primary,
        confidence=0.9,
        reason="test",
        query_plan=_plan(),
        supporting_agents=supporting,
    )


def _tutor_result(topic: str = "residuals") -> AgentResult:
    return AgentResult(
        answer="残差是观测值与拟合值之差 [c1]",
        evidence_status="sufficient",
        model_name="tutor-model",
        tool_calls=[ToolCall("search_course_material", ok=True, latency_ms=5)],
        shared={"explained_topic": topic},
    )


def _quiz_result() -> AgentResult:
    return AgentResult(
        answer="已为你生成 3 道题。",
        evidence_status="practice_created",
        model_name="quiz-model",
        practice_set={"title": "residual practice"},
    )


def _orchestrator(registry: dict) -> LearningAgentOrchestrator:
    return LearningAgentOrchestrator(registry=registry, clarify_agent=ClarifyAgent())


async def test_single_agent_turn_runs_only_the_primary_agent() -> None:
    tutor = _RecordingAgent(AgentName.TUTOR, _tutor_result())
    quiz = _RecordingAgent(AgentName.QUIZ, _quiz_result())
    decision = decision_for(
        LearningIntent.COURSE_QA, confidence=0.9, reason="test", query_plan=_plan()
    )

    result, trace = await _orchestrator(
        {AgentName.TUTOR: tutor, AgentName.QUIZ: quiz}
    ).run(_context(decision))

    assert trace.as_dict()["agent_sequence"] == ["tutor"]
    assert quiz.tasks == []
    assert result.answer == _tutor_result().answer


async def test_sequential_turn_runs_supporting_agent_and_merges_output() -> None:
    tutor = _RecordingAgent(AgentName.TUTOR, _tutor_result())
    quiz = _RecordingAgent(AgentName.QUIZ, _quiz_result())
    decision = _sequential(LearningIntent.CONCEPT_EXPLANATION, [AgentName.QUIZ])

    result, trace = await _orchestrator(
        {AgentName.TUTOR: tutor, AgentName.QUIZ: quiz}
    ).run(_context(decision))

    assert trace.as_dict()["agent_sequence"] == ["tutor", "quiz"]
    assert decision.execution_mode == ExecutionMode.SEQUENTIAL
    assert "残差是观测值" in result.answer and "已为你生成 3 道题" in result.answer
    assert result.practice_set == {"title": "residual practice"}
    # The primary agent's evidence must survive the merge so citations still resolve.
    assert result.evidence_status == "sufficient"


async def test_supporting_agent_receives_the_primary_agents_output() -> None:
    tutor = _RecordingAgent(AgentName.TUTOR, _tutor_result(topic="ANOVA assumptions"))
    quiz = _RecordingAgent(AgentName.QUIZ, _quiz_result())
    decision = _sequential(LearningIntent.CONCEPT_EXPLANATION, [AgentName.QUIZ])

    await _orchestrator({AgentName.TUTOR: tutor, AgentName.QUIZ: quiz}).run(
        _context(decision)
    )

    assert quiz.tasks[0].inputs["topic"] == "ANOVA assumptions"


async def test_supporting_agent_is_skipped_without_its_dependency() -> None:
    silent_tutor = _RecordingAgent(
        AgentName.TUTOR, AgentResult(answer="no material found", shared={})
    )
    quiz = _RecordingAgent(AgentName.QUIZ, _quiz_result())
    decision = _sequential(LearningIntent.CONCEPT_EXPLANATION, [AgentName.QUIZ])

    result, trace = await _orchestrator(
        {AgentName.TUTOR: silent_tutor, AgentName.QUIZ: quiz}
    ).run(_context(decision))

    assert quiz.tasks == []
    assert result.answer == "no material found"
    skipped = trace.steps[-1]
    assert skipped.status == AgentStatus.SKIPPED
    assert "explained_topic" in (skipped.note or "")


async def test_failing_supporting_agent_preserves_the_primary_answer() -> None:
    tutor = _RecordingAgent(AgentName.TUTOR, _tutor_result())
    decision = _sequential(LearningIntent.CONCEPT_EXPLANATION, [AgentName.QUIZ])

    result, trace = await _orchestrator(
        {AgentName.TUTOR: tutor, AgentName.QUIZ: _FailingAgent(AgentName.QUIZ)}
    ).run(_context(decision))

    assert result.answer == _tutor_result().answer
    assert trace.steps[-1].status == AgentStatus.FAILED
    assert trace.steps[-1].note == "RuntimeError"


async def test_clarification_turn_bypasses_every_agent() -> None:
    tutor = _RecordingAgent(AgentName.TUTOR, _tutor_result())
    decision = decision_for(
        LearningIntent.COURSE_QA, confidence=0.2, reason="unclear", query_plan=_plan()
    )
    decision = RoutingDecision(
        intent=decision.intent,
        primary_agent=decision.primary_agent,
        supporting_agents=[],
        execution_mode=ExecutionMode.CLARIFY,
        confidence=0.2,
        reason="unclear",
        query_plan=_plan(),
        clarification="你想问什么？",
        target=RouteTarget.CLARIFY,
    )

    result, trace = await _orchestrator({AgentName.TUTOR: tutor}).run(_context(decision))

    assert tutor.tasks == []
    assert result.answer == "你想问什么？"
    assert result.evidence_status == "clarification"


async def test_unregistered_primary_agent_falls_back_to_the_tutor() -> None:
    tutor = _RecordingAgent(AgentName.TUTOR, _tutor_result())
    decision = decision_for(
        LearningIntent.ANSWER_EVALUATION, confidence=0.9, reason="test", query_plan=_plan()
    )

    result, trace = await _orchestrator({AgentName.TUTOR: tutor}).run(_context(decision))

    assert decision.primary_agent == AgentName.EVALUATOR
    assert trace.as_dict()["agent_sequence"] == ["tutor"]
    assert result.answer == _tutor_result().answer


async def test_trace_records_route_tool_calls_and_timing() -> None:
    tutor = _RecordingAgent(AgentName.TUTOR, _tutor_result())
    decision = decision_for(
        LearningIntent.COURSE_QA, confidence=0.9, reason="test", query_plan=_plan()
    )

    _, trace = await _orchestrator({AgentName.TUTOR: tutor}).run(_context(decision))
    payload = trace.as_dict()

    assert payload["route"]["intent"] == "course_qa"
    assert payload["steps"][0]["tool_calls"][0]["name"] == "search_course_material"
    assert payload["steps"][0]["role"] == "primary"
    assert payload["trace_id"]
    assert payload["total_latency_ms"] >= 0
