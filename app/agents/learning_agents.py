"""Learning agents, implemented as thin adapters over the existing services.

Roadmap section 4.2 is explicit that stable services must not be rewritten to
introduce the agent layer. Each agent therefore owns only its task framing and
result shaping; the retrieval, generation, grading and planning behaviour stays
in the services that are already covered by tests and offline evaluations.
"""

from app.agents.presenters import (
    _document_inventory_answer,
    _evidence_status,
    _general_answer,
    _practice_configuration,
    _practice_created_answer,
    _progress_answer,
    _study_plan_answer,
)
from app.agents.protocol import (
    AgentResult,
    AgentStatus,
    AgentTask,
    LearningContext,
    ToolCall,
    timer,
)
from app.agents.routing import AgentName
from app.llm.gateway import GeneratedAnswer, TutorAnswerGateway, _extractive_answer
from app.rag.retrieval import CourseRetriever


class TutorAgent:
    """Grounded course answers: retrieve, then generate with citations."""

    name = AgentName.TUTOR

    def __init__(self, retriever: CourseRetriever, gateway: TutorAnswerGateway) -> None:
        self.retriever = retriever
        self.gateway = gateway

    async def run(self, task: AgentTask, context: LearningContext) -> AgentResult:
        plan = context.decision.query_plan
        calls: list[ToolCall] = []

        with timer() as retrieval:
            evidence = await self.retriever.retrieve(
                user_id=context.user_id,
                course_id=context.course_id,
                query=plan.standalone_query,
                top_k=plan.top_k,
                document_types=plan.document_types or None,
                document_ids=plan.document_ids or None,
                page_from=plan.page_from,
                page_to=plan.page_to,
            )
        calls.append(
            ToolCall(
                "search_course_material",
                ok=True,
                latency_ms=retrieval.elapsed_ms,
                detail=f"{len(evidence)} chunk(s)",
            )
        )

        status = _evidence_status(evidence)
        if not evidence:
            generated = _extractive_answer(evidence, reason="insufficient_evidence")
            return AgentResult(
                answer=generated.answer,
                status=AgentStatus.DEGRADED,
                evidence_status=status,
                evidence=evidence,
                model_name=generated.model_name,
                fallback_reason=generated.fallback_reason,
                tool_calls=calls,
            )

        with timer() as generation:
            generated = await self.gateway.answer(
                question=context.message,
                language=context.language,
                mode=context.mode,
                evidence=evidence,
                history=context.history_pairs(),
            )
        calls.append(
            ToolCall(
                "generate_tutor_answer",
                ok=generated.fallback_reason is None,
                latency_ms=generation.elapsed_ms,
                detail=generated.fallback_reason,
            )
        )
        return AgentResult(
            answer=generated.answer,
            status=AgentStatus.DEGRADED if generated.fallback_reason else AgentStatus.OK,
            evidence_status=status,
            evidence=evidence,
            model_name=generated.model_name,
            input_tokens=generated.input_tokens,
            output_tokens=generated.output_tokens,
            fallback_reason=generated.fallback_reason,
            tool_calls=calls,
            # A following QuizAgent should build questions on what was just taught.
            shared={"explained_topic": plan.standalone_query},
        )


class QuizAgent:
    """Creates a gradable practice set for the current learning scope."""

    name = AgentName.QUIZ

    def __init__(self, practice_service) -> None:
        self.practice_service = practice_service

    async def run(self, task: AgentTask, context: LearningContext) -> AgentResult:
        topic = task.inputs.get("topic") or context.learned_topic
        configuration = _practice_configuration(
            context.message,
            context.language,
            context.scope,
            options=context.practice_options,
            context_topic=topic,
        )
        with timer() as creation:
            practice_set = await self.practice_service.create(
                context.user_id, context.course_id, configuration
            )
        return AgentResult(
            answer=_practice_created_answer(practice_set, context.language),
            evidence_status="practice_created",
            model_name=practice_set.model_name,
            practice_set=practice_set,
            tool_calls=[
                ToolCall(
                    "create_practice_set",
                    ok=True,
                    latency_ms=creation.elapsed_ms,
                    detail=f"{len(practice_set.questions)} question(s)",
                )
            ],
        )


class CatalogAgent:
    """Answers questions about which materials exist, never about their content."""

    name = AgentName.CATALOG

    def __init__(self, document_repository) -> None:
        self.document_repository = document_repository

    async def run(self, task: AgentTask, context: LearningContext) -> AgentResult:
        with timer() as lookup:
            documents = await self.document_repository.list_for_course(
                context.user_id, context.course_id, offset=0, limit=100
            )
        return AgentResult(
            answer=_document_inventory_answer(documents, context.language),
            evidence_status="catalog",
            model_name="course-catalog",
            tool_calls=[
                ToolCall(
                    "list_course_documents",
                    ok=True,
                    latency_ms=lookup.elapsed_ms,
                    detail=f"{len(documents)} document(s)",
                )
            ],
        )


class ProgressAgent:
    """Reports mastery and weak topics from recorded attempts."""

    name = AgentName.PROGRESS

    def __init__(self, progress_repository) -> None:
        self.progress_repository = progress_repository

    async def run(self, task: AgentTask, context: LearningContext) -> AgentResult:
        with timer() as lookup:
            topics = await self.progress_repository.list_topics(
                context.user_id, context.course_id
            )
            total_attempts = await self.progress_repository.count_attempts(
                context.user_id, context.course_id
            )
        weak = [
            getattr(topic, "topic", None)
            for topic in topics
            if getattr(topic, "mastery_level", 1.0) < 0.6
        ]
        return AgentResult(
            answer=_progress_answer(topics, total_attempts, context.language),
            evidence_status="business_data",
            model_name="progress-service",
            tool_calls=[
                ToolCall(
                    "get_learning_progress",
                    ok=True,
                    latency_ms=lookup.elapsed_ms,
                    detail=f"{len(topics)} topic(s), {total_attempts} attempt(s)",
                )
            ],
            # A following PlannerAgent should target what the learner is weak at.
            shared={"weak_topics": [item for item in weak if item]},
        )


class PlannerAgent:
    """Reads existing study plans. Plan generation is still roadmap step 5."""

    name = AgentName.PLANNER

    def __init__(self, study_plan_repository) -> None:
        self.study_plan_repository = study_plan_repository

    async def run(self, task: AgentTask, context: LearningContext) -> AgentResult:
        with timer() as lookup:
            plans = await self.study_plan_repository.list_for_course(
                context.user_id, context.course_id, offset=0, limit=5
            )
        return AgentResult(
            answer=_study_plan_answer(plans, context.language),
            evidence_status="business_data",
            model_name="study-plan-service",
            tool_calls=[
                ToolCall(
                    "list_study_plans",
                    ok=True,
                    latency_ms=lookup.elapsed_ms,
                    detail=f"{len(plans)} plan(s)",
                )
            ],
        )


class GeneralAgent:
    """Greetings and capability questions. Never touches course data."""

    name = AgentName.GENERAL

    async def run(self, task: AgentTask, context: LearningContext) -> AgentResult:
        return AgentResult(
            answer=_general_answer(context.language),
            evidence_status="general",
            model_name="general-router",
        )


class ClarifyAgent:
    """Asks one question back when routing confidence was too low to act."""

    name = AgentName.GENERAL

    async def run(self, task: AgentTask, context: LearningContext) -> AgentResult:
        return AgentResult(
            answer=context.decision.clarification or _general_answer(context.language),
            evidence_status="clarification",
            model_name="intent-router",
        )
