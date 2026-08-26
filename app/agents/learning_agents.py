"""Learning agents, implemented as thin adapters over the existing services.

Roadmap section 4.2 is explicit that stable services must not be rewritten to
introduce the agent layer. Each agent therefore owns only its task framing and
result shaping; the retrieval, generation, grading and planning behaviour stays
in the services that are already covered by tests and offline evaluations.
"""

from app.agents.presenters import (
    _attempt_feedback_answer,
    _document_inventory_answer,
    _evidence_status,
    _general_answer,
    _practice_configuration,
    _practice_created_answer,
    _answer_format_mismatch_answer,
    _no_pending_question_answer,
    _progress_answer,
    _requests_new_plan,
    _study_plan_answer,
    _study_plan_configuration,
    _study_plan_created_answer,
    _extract_submitted_answer,
)
from app.schemas.attempt import AttemptCreate
from app.agents.protocol import (
    AgentResult,
    AgentStatus,
    AgentTask,
    LearningContext,
    ToolCall,
    timer,
)
from app.agents.routing import AgentName
from app.core.exceptions import AppError
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
    """Reads existing study plans, and builds a new one when asked to.

    `StudyPlanService.create` already orders topics by recorded mastery, so plan
    generation here is a matter of invoking it with the learner's weak topics
    rather than duplicating the scheduling logic.
    """

    name = AgentName.PLANNER

    def __init__(self, study_plan_repository, study_plan_service=None) -> None:
        self.study_plan_repository = study_plan_repository
        self.study_plan_service = study_plan_service

    async def run(self, task: AgentTask, context: LearningContext) -> AgentResult:
        wants_new_plan = task.inputs.get("create") or _requests_new_plan(context.message)
        if wants_new_plan and self.study_plan_service is not None:
            return await self._create(task, context)
        return await self._list(context)

    async def _create(self, task: AgentTask, context: LearningContext) -> AgentResult:
        configuration = _study_plan_configuration(context.message)
        with timer() as creation:
            plan = await self.study_plan_service.create(
                context.user_id, context.course_id, configuration
            )
        weak_topics = task.inputs.get("weak_topics") or []
        return AgentResult(
            answer=_study_plan_created_answer(plan, weak_topics, context.language),
            evidence_status="business_data",
            model_name="study-plan-service",
            tool_calls=[
                ToolCall(
                    "create_study_plan",
                    ok=True,
                    latency_ms=creation.elapsed_ms,
                    detail=f"{len(plan.tasks)} task(s)",
                )
            ],
            shared={"study_plan_id": str(plan.id)},
        )

    async def _list(self, context: LearningContext) -> AgentResult:
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


class EvaluatorAgent:
    """Grades an answer the learner typed in the conversation.

    The question is resolved from the newest practice set instead of being named
    by the learner, and grading itself stays in `AttemptService` so the immutable
    rubric and the recorded evaluation baseline continue to apply unchanged.
    """

    name = AgentName.EVALUATOR

    def __init__(self, attempt_service, practice_repository) -> None:
        self.attempt_service = attempt_service
        self.practice_repository = practice_repository

    async def run(self, task: AgentTask, context: LearningContext) -> AgentResult:
        with timer() as lookup:
            question = await self.practice_repository.latest_pending_question(
                context.user_id, context.course_id
            )
        calls = [
            ToolCall(
                "find_pending_question",
                ok=question is not None,
                latency_ms=lookup.elapsed_ms,
                detail=None if question else "no unanswered question",
            )
        ]
        if question is None:
            return AgentResult(
                answer=_no_pending_question_answer(context.language),
                status=AgentStatus.SKIPPED,
                evidence_status="general",
                model_name="attempt-service",
                tool_calls=calls,
            )

        answer_text = _extract_submitted_answer(context.message, question)
        with timer() as grading:
            try:
                attempt = await self.attempt_service.submit(
                    context.user_id,
                    question.id,
                    AttemptCreate(answer=answer_text),
                )
            except AppError as error:
                if error.code not in {"INVALID_OPTION", "EMPTY_ANSWER"}:
                    raise
                # Tell the learner how to answer instead of failing the request.
                calls.append(
                    ToolCall(
                        "grade_answer",
                        ok=False,
                        latency_ms=grading.elapsed_ms,
                        detail=error.code,
                    )
                )
                return AgentResult(
                    answer=_answer_format_mismatch_answer(question, context.language),
                    status=AgentStatus.SKIPPED,
                    evidence_status="general",
                    model_name="attempt-service",
                    tool_calls=calls,
                )
        calls.append(
            ToolCall(
                "grade_answer",
                ok=True,
                latency_ms=grading.elapsed_ms,
                detail=f"score {attempt.score}",
            )
        )
        # Topics, not error prose: knowledge_errors describes what went wrong,
        # while the planner needs subjects it can schedule study time against.
        feedback = attempt.feedback
        weak = (
            list(feedback.recommended_topics or [])
            or list(feedback.missing_concepts or [])
            or list(question.knowledge_points_json or [])
        )
        return AgentResult(
            answer=_attempt_feedback_answer(question, attempt, context.language),
            evidence_status="graded",
            model_name=attempt.evaluation_model,
            tool_calls=calls,
            # A following PlannerAgent should target what was just answered badly.
            shared={"weak_topics": weak, "last_score": attempt.score},
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
