from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.agents.learning_agents import EvaluatorAgent, PlannerAgent
from app.agents.presenters import (
    _extract_submitted_answer,
    _requests_new_plan,
    _study_plan_configuration,
)
from app.agents.protocol import AgentStatus, AgentTask, LearningContext
from app.agents.routing import AgentName, LearningIntent, QueryPlan, decision_for
from app.core.exceptions import AppError
from app.schemas.practice import QuestionType
from app.schemas.tutor import TutorScope


COURSE_ID = UUID("00000000-0000-0000-0000-000000000010")
USER_ID = UUID("00000000-0000-0000-0000-000000000011")


def _context(message: str) -> LearningContext:
    plan = QueryPlan(
        standalone_query=message,
        course_id=COURSE_ID,
        document_types=[],
        document_ids=[],
        page_from=None,
        page_to=None,
        requested_language="zh",
        top_k=8,
    )
    return LearningContext(
        user_id=USER_ID,
        course_id=COURSE_ID,
        conversation_id=uuid4(),
        message=message,
        language="zh",
        mode="standard",
        scope=TutorScope(),
        decision=decision_for(
            LearningIntent.ANSWER_EVALUATION, confidence=0.96, reason="t", query_plan=plan
        ),
    )


def _question(question_type: str = "short_answer"):
    return SimpleNamespace(
        id=uuid4(),
        content="残差的定义是什么？",
        question_type=question_type,
        options_json=[{"id": "A", "is_correct": True}, {"id": "B"}],
        knowledge_points_json=["残差"],
    )


def _attempt(score: float = 40.0):
    return SimpleNamespace(
        score=score,
        max_score=100,
        evaluation_model="eval-model",
        feedback=SimpleNamespace(
            summary="部分正确",
            knowledge_errors=["把残差与误差混为一谈。"],
            missing_concepts=["观测值与拟合值之差"],
            recommended_topics=["残差定义", "误差与残差的区别"],
        ),
    )


class _Repo:
    def __init__(self, question=None) -> None:
        self.question = question

    async def latest_pending_question(self, user_id, course_id):
        return self.question


class _AttemptService:
    def __init__(self, attempt=None, error: Exception | None = None) -> None:
        self.attempt = attempt
        self.error = error
        self.submitted: list = []

    async def submit(self, user_id, question_id, data):
        self.submitted.append(data.answer)
        if self.error:
            raise self.error
        return self.attempt


async def test_evaluator_grades_the_latest_pending_question() -> None:
    service = _AttemptService(_attempt())
    agent = EvaluatorAgent(service, _Repo(_question()))

    result = await agent.run(
        AgentTask(AgentName.EVALUATOR, "grade"), _context("我的答案是：残差是观测值减去拟合值")
    )

    assert service.submitted == ["残差是观测值减去拟合值"]
    assert result.evidence_status == "graded"
    assert "40.0 / 100" in result.answer


async def test_evaluator_passes_topics_not_error_prose_to_the_planner() -> None:
    agent = EvaluatorAgent(_AttemptService(_attempt()), _Repo(_question()))

    result = await agent.run(AgentTask(AgentName.EVALUATOR, "grade"), _context("我选 A"))

    # knowledge_errors describes the mistake; the planner needs schedulable topics.
    assert result.shared["weak_topics"] == ["残差定义", "误差与残差的区别"]


async def test_evaluator_reports_when_nothing_is_waiting_to_be_graded() -> None:
    agent = EvaluatorAgent(_AttemptService(_attempt()), _Repo(None))

    result = await agent.run(AgentTask(AgentName.EVALUATOR, "grade"), _context("我选 A"))

    assert result.status == AgentStatus.SKIPPED
    assert "没有待作答" in result.answer


async def test_evaluator_explains_the_expected_format_instead_of_failing() -> None:
    service = _AttemptService(error=AppError("INVALID_OPTION", "答案必须是题目中的选项编号"))
    agent = EvaluatorAgent(service, _Repo(_question(QuestionType.SINGLE_CHOICE.value)))

    result = await agent.run(
        AgentTask(AgentName.EVALUATOR, "grade"), _context("我的答案是：中心化就是把数据变成0")
    )

    assert result.status == AgentStatus.SKIPPED
    assert "选项编号" in result.answer


async def test_evaluator_reraises_unexpected_errors() -> None:
    service = _AttemptService(error=AppError("QUESTION_DATA_INVALID", "题目缺少正确答案"))
    agent = EvaluatorAgent(service, _Repo(_question()))

    with pytest.raises(AppError):
        await agent.run(AgentTask(AgentName.EVALUATOR, "grade"), _context("我选 A"))


class _PlanRepo:
    async def list_for_course(self, user_id, course_id, *, offset, limit):
        return []


class _PlanService:
    def __init__(self) -> None:
        self.created: list = []

    async def create(self, user_id, course_id, data):
        self.created.append(data)
        return SimpleNamespace(
            id=uuid4(),
            title="Linear model 学习计划",
            start_date="2026-09-01",
            end_date="2026-09-07",
            daily_minutes=data.daily_minutes,
            tasks=[1, 2, 3],
        )


async def test_planner_creates_a_plan_when_the_workflow_asks_for_one() -> None:
    service = _PlanService()
    agent = PlannerAgent(_PlanRepo(), service)

    result = await agent.run(
        AgentTask(AgentName.PLANNER, "plan", inputs={"create": True, "weak_topics": ["残差"]}),
        _context("批改完帮我安排复习"),
    )

    assert service.created
    assert "重点针对：残差" in result.answer
    assert result.shared["study_plan_id"]


async def test_planner_only_reads_when_the_learner_asks_to_see_a_plan() -> None:
    service = _PlanService()
    agent = PlannerAgent(_PlanRepo(), service)

    await agent.run(AgentTask(AgentName.PLANNER, "plan"), _context("查看我的学习计划"))

    assert service.created == []


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("帮我制定一份7天复习计划", True),
        ("生成一份备考计划", True),
        ("查看我的学习计划", False),
        ("我的学习计划完成了多少", False),
    ],
)
def test_plan_creation_intent_is_distinguished_from_plan_reading(message, expected) -> None:
    assert _requests_new_plan(message) is expected


def test_plan_configuration_reads_duration_and_daily_time() -> None:
    configuration = _study_plan_configuration("每天90分钟，帮我生成一份14天备考计划")

    assert configuration.duration_days == 14
    assert configuration.daily_minutes == 90


@pytest.mark.parametrize(
    ("message", "question_type", "expected"),
    [
        ("我选 C", QuestionType.SINGLE_CHOICE.value, "C"),
        ("我的答案是 B", QuestionType.SINGLE_CHOICE.value, "B"),
        ("答案：残差是观测值减去拟合值", "short_answer", "残差是观测值减去拟合值"),
        ("我的答案是：残差就是误差", "short_answer", "残差就是误差"),
    ],
)
def test_submitted_answer_is_stripped_of_its_framing(message, question_type, expected) -> None:
    assert _extract_submitted_answer(message, _question(question_type)) == expected
