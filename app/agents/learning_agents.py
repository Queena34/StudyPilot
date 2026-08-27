"""Learning agents, implemented as thin adapters over the existing services.

Roadmap section 4.2 is explicit that stable services must not be rewritten to
introduce the agent layer. Each agent therefore owns only its task framing and
result shaping; the retrieval, generation, grading and planning behaviour stays
in the services that are already covered by tests and offline evaluations.
"""

from app.agents.presenters import (
    _attempt_feedback_answer,
    _document_inventory_answer,
    _with_integrity_notice,
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
)
from app.agents.routing import AgentName
from app.agents.skills import get_skill_library
from app.core.exceptions import AppError
from app.llm.gateway import GeneratedAnswer, TutorAnswerGateway, _extractive_answer


class TutorAgent:
    """Grounded course answers: retrieve, then generate with citations."""

    name = AgentName.TUTOR

    def __init__(self, gateway: TutorAnswerGateway) -> None:
        self.gateway = gateway

    async def run(self, task: AgentTask, context: LearningContext) -> AgentResult:
        plan = context.decision.query_plan
        tools = context.tools.session()
        evidence = await tools.search_course_material(
            context,
            query=plan.search_query,
            top_k=plan.top_k,
            document_types=plan.document_types,
            document_ids=plan.document_ids,
            page_from=plan.page_from,
            page_to=plan.page_to,
            chapter=plan.chapter,
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
                tool_calls=tools.calls,
            )

        integrity = context.integrity
        generated = await self.gateway.answer(
            question=context.message,
            language=context.language,
            mode=context.mode,
            evidence=evidence,
            history=context.history_pairs(),
            answer_constraint=getattr(integrity, "answer_constraint", ""),
            teaching_guidance=get_skill_library().prompt_section(
                message=context.message, agent=self.name.value
            ),
        )
        answer = _with_integrity_notice(generated.answer, integrity)
        return AgentResult(
            answer=answer,
            status=AgentStatus.DEGRADED if generated.fallback_reason else AgentStatus.OK,
            evidence_status=status,
            evidence=evidence,
            model_name=generated.model_name,
            input_tokens=generated.input_tokens,
            output_tokens=generated.output_tokens,
            fallback_reason=generated.fallback_reason,
            tool_calls=tools.calls,
            # A following QuizAgent should build questions on what was just taught.
            shared={"explained_topic": plan.search_query},
        )


class QuizAgent:
    """Creates a gradable practice set for the current learning scope."""

    name = AgentName.QUIZ

    async def run(self, task: AgentTask, context: LearningContext) -> AgentResult:
        topic = task.inputs.get("topic") or context.learned_topic
        plan = context.decision.query_plan
        # The scope comes from the routed plan, not from re-reading the message.
        scope = context.scope.model_copy(update={"chapter": plan.chapter})
        configuration = _practice_configuration(
            context.message,
            context.language,
            scope,
            options=context.practice_options,
            context_topic=topic,
        )
        tools = context.tools.session()
        practice_set = await tools.create_practice_set(context, configuration)
        return AgentResult(
            answer=_practice_created_answer(practice_set, context.language),
            evidence_status="practice_created",
            model_name=practice_set.model_name,
            practice_set=practice_set,
            tool_calls=tools.calls,
        )


class CatalogAgent:
    """Answers questions about which materials exist, never about their content."""

    name = AgentName.CATALOG

    async def run(self, task: AgentTask, context: LearningContext) -> AgentResult:
        tools = context.tools.session()
        documents = await tools.list_course_documents(context)
        return AgentResult(
            answer=_document_inventory_answer(documents, context.language),
            evidence_status="catalog",
            model_name="course-catalog",
            tool_calls=tools.calls,
        )


class ProgressAgent:
    """Reports mastery and weak topics from recorded attempts."""

    name = AgentName.PROGRESS

    async def run(self, task: AgentTask, context: LearningContext) -> AgentResult:
        tools = context.tools.session()
        topics, total_attempts = await tools.get_learning_progress(context)
        weak = [
            getattr(topic, "display_topic", None) or getattr(topic, "topic", None)
            for topic in topics
            if getattr(topic, "mastery_score", 1.0) < 0.6
        ]
        return AgentResult(
            answer=_progress_answer(topics, total_attempts, context.language),
            evidence_status="business_data",
            model_name="progress-service",
            tool_calls=tools.calls,
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

    async def run(self, task: AgentTask, context: LearningContext) -> AgentResult:
        tools = context.tools.session()
        wants_new_plan = task.inputs.get("create") or _requests_new_plan(context.message)
        if wants_new_plan and context.tools.study_plan_service is not None:
            configuration = _study_plan_configuration(context.message)
            plan = await tools.create_study_plan(context, configuration)
            return AgentResult(
                answer=_study_plan_created_answer(
                    plan, task.inputs.get("weak_topics") or [], context.language
                ),
                evidence_status="business_data",
                model_name="study-plan-service",
                tool_calls=tools.calls,
                shared={"study_plan_id": str(plan.id)},
            )
        plans = await tools.list_study_plans(context)
        return AgentResult(
            answer=_study_plan_answer(plans, context.language),
            evidence_status="business_data",
            model_name="study-plan-service",
            tool_calls=tools.calls,
        )


class EvaluatorAgent:
    """Grades an answer the learner typed in the conversation.

    The question is resolved from the newest practice set instead of being named
    by the learner, and grading itself stays in `AttemptService` so the immutable
    rubric and the recorded evaluation baseline continue to apply unchanged.
    """

    name = AgentName.EVALUATOR

    async def run(self, task: AgentTask, context: LearningContext) -> AgentResult:
        tools = context.tools.session()
        question = await tools.find_pending_question(context)
        if question is None:
            return AgentResult(
                answer=_no_pending_question_answer(context.language),
                status=AgentStatus.SKIPPED,
                evidence_status="general",
                model_name="attempt-service",
                tool_calls=tools.calls,
            )

        answer_text = _extract_submitted_answer(context.message, question)
        try:
            attempt = await tools.grade_answer(
                context, question.id, AttemptCreate(answer=answer_text)
            )
        except AppError as error:
            if error.code not in {"INVALID_OPTION", "EMPTY_ANSWER"}:
                raise
            # Tell the learner how to answer instead of failing the request.
            return AgentResult(
                answer=_answer_format_mismatch_answer(question, context.language),
                status=AgentStatus.SKIPPED,
                evidence_status="general",
                model_name="attempt-service",
                tool_calls=tools.calls,
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
            tool_calls=tools.calls,
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


class IntegrityGuardAgent:
    """Answers when the guard blocks a direct answer, so no course agent runs."""

    name = AgentName.GENERAL

    async def run(self, task: AgentTask, context: LearningContext) -> AgentResult:
        return AgentResult(
            answer=context.integrity.notice,
            status=AgentStatus.SKIPPED,
            evidence_status="integrity_blocked",
            model_name="integrity-guard",
        )
