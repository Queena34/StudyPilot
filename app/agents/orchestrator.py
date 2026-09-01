"""Learning agent orchestration (roadmap section 4.2).

Selects the primary agent from the routing decision, runs supporting agents when
the decision asks for a sequential workflow, passes context between them, and
records every step in an `AgentTrace`. A failing supporting agent degrades the
turn instead of losing the primary answer the learner already earned.
"""

from app.agents.protocol import (
    AgentResult,
    AgentStatus,
    AgentStep,
    AgentTask,
    AgentTrace,
    LearningContext,
    timer,
)
from app.agents.integrity import IntegrityLevel
from app.agents.routing import AgentName, ExecutionMode, RouteTarget, RoutingSource

#: Supporting agents only run when the primary agent produced what they consume.
_SUPPORTING_DEPENDENCIES: dict[AgentName, str] = {
    AgentName.QUIZ: "explained_topic",
    AgentName.PLANNER: "weak_topics",
}

#: Supporting agents that must build something rather than read existing state.
_SUPPORTING_CREATES: frozenset[AgentName] = frozenset({AgentName.PLANNER})

#: Agents that produce course answers or graded practice, so the guard applies.
_INTEGRITY_GUARDED: frozenset[AgentName] = frozenset(
    {AgentName.TUTOR, AgentName.QUIZ, AgentName.EVALUATOR}
)

_OBJECTIVES: dict[AgentName, str] = {
    AgentName.TUTOR: "Answer the learner's question from the course material with citations.",
    AgentName.QUIZ: "Create a gradable practice set for the current learning scope.",
    AgentName.EVALUATOR: "Grade the learner's answer against the immutable rubric.",
    AgentName.PLANNER: "Report or build the learner's study plan.",
    AgentName.PROGRESS: "Report mastery and weak topics.",
    AgentName.CATALOG: "List the course materials that exist.",
    AgentName.GENERAL: "Answer a greeting or a capability question.",
}


class LearningAgentOrchestrator:
    """Dispatches one learning turn across one or more agents."""

    def __init__(
        self,
        registry: dict[AgentName, object],
        clarify_agent: object,
        integrity_agent: object | None = None,
    ) -> None:
        self.registry = registry
        self.clarify_agent = clarify_agent
        self.integrity_agent = integrity_agent

    async def run(self, context: LearningContext) -> tuple[AgentResult, AgentTrace]:
        decision = context.decision
        trace = AgentTrace(route=decision.as_dict())

        with timer() as total:
            integrity = context.integrity
            if (
                integrity is not None
                and integrity.blocks_direct_answer
                and self.integrity_agent is not None
                and decision.primary_agent in _INTEGRITY_GUARDED
            ):
                # No course agent runs: the turn is answered by the guard alone.
                trace.route = {**trace.route, "integrity": integrity.as_dict()}
                result = await self._step(
                    self.integrity_agent,
                    AgentName.GENERAL,
                    "integrity_guard",
                    AgentTask(AgentName.GENERAL, "Decline to answer during a live exam."),
                    context,
                    trace,
                )
            elif decision.target == RouteTarget.CLARIFY:
                result = await self._step(
                    self.clarify_agent,
                    AgentName.GENERAL,
                    "clarify",
                    AgentTask(AgentName.GENERAL, "Ask the learner to clarify their request."),
                    context,
                    trace,
                )
            else:
                if integrity is not None:
                    trace.route = {**trace.route, "integrity": integrity.as_dict()}
                result = await self._run_workflow(context, trace)

        trace.total_latency_ms = total.elapsed_ms
        return result, trace

    async def _run_workflow(
        self, context: LearningContext, trace: AgentTrace
    ) -> AgentResult:
        decision = context.decision
        primary_name = decision.primary_agent
        integrity = context.integrity
        if (
            integrity is not None
            and integrity.level is not IntegrityLevel.LEARNING_ALLOWED
            and decision.source is not RoutingSource.RULE
        ):
            # PRD 8.7 requires the notice to arrive with real help, so a restricted
            # turn is answered from the course material rather than deflected. An
            # explicit rule match still wins: "我选 C" really is a submission.
            primary_name = AgentName.TUTOR
        primary_agent = self.registry.get(primary_name)
        if primary_agent is None:
            # An intent with no registered agent must not break the turn.
            primary_name = AgentName.TUTOR
            primary_agent = self.registry[AgentName.TUTOR]

        result = await self._step(
            primary_agent,
            primary_name,
            "primary",
            AgentTask(primary_name, _OBJECTIVES.get(primary_name, "Handle the request.")),
            context,
            trace,
        )
        context.shared.update(result.shared)

        if decision.execution_mode != ExecutionMode.SEQUENTIAL:
            return result
        for supporting_name in decision.supporting_agents:
            result = await self._run_supporting(supporting_name, context, trace, result)
        return result

    async def _run_supporting(
        self,
        supporting_name: AgentName,
        context: LearningContext,
        trace: AgentTrace,
        primary_result: AgentResult,
    ) -> AgentResult:
        agent = self.registry.get(supporting_name)
        dependency = _SUPPORTING_DEPENDENCIES.get(supporting_name)
        if agent is None or (dependency and not context.shared.get(dependency)):
            trace.steps.append(
                AgentStep(
                    agent=supporting_name,
                    role="supporting",
                    status=AgentStatus.SKIPPED,
                    latency_ms=0,
                    model_name="none",
                    note=(
                        "no registered agent"
                        if agent is None
                        else f"primary agent produced no {dependency}"
                    ),
                )
            )
            return primary_result

        task = AgentTask(
            supporting_name,
            _OBJECTIVES.get(supporting_name, "Continue the workflow."),
            inputs=_supporting_inputs(supporting_name, context),
        )
        try:
            supporting_result = await self._step(
                agent, supporting_name, "supporting", task, context, trace
            )
        except Exception as error:  # noqa: BLE001 - a follow-up must not lose the answer
            trace.steps.append(
                AgentStep(
                    agent=supporting_name,
                    role="supporting",
                    status=AgentStatus.FAILED,
                    latency_ms=0,
                    model_name="none",
                    note=type(error).__name__,
                )
            )
            return primary_result

        context.shared.update(supporting_result.shared)
        return _merge(primary_result, supporting_result)

    async def _step(
        self,
        agent: object,
        name: AgentName,
        role: str,
        task: AgentTask,
        context: LearningContext,
        trace: AgentTrace,
    ) -> AgentResult:
        with timer() as elapsed:
            result = await agent.run(task, context)
        trace.steps.append(
            AgentStep(
                agent=name,
                role=role,
                status=result.status,
                latency_ms=elapsed.elapsed_ms,
                model_name=result.model_name,
                tool_calls=result.tool_calls,
                fallback_reason=result.fallback_reason,
            )
        )
        return result


def _supporting_inputs(name: AgentName, context: LearningContext) -> dict:
    if name == AgentName.QUIZ:
        return {"topic": context.shared.get("explained_topic")}
    if name == AgentName.PLANNER:
        return {
            "weak_topics": context.shared.get("weak_topics", []),
            "create": AgentName.PLANNER in _SUPPORTING_CREATES,
        }
    return {}


def _merge(primary: AgentResult, supporting: AgentResult) -> AgentResult:
    """Keep the primary answer and evidence; append what the follow-up produced."""

    return AgentResult(
        answer=f"{primary.answer}\n\n---\n\n{supporting.answer}",
        status=(
            AgentStatus.DEGRADED
            if AgentStatus.DEGRADED in {primary.status, supporting.status}
            else AgentStatus.OK
        ),
        evidence_status=primary.evidence_status,
        evidence=primary.evidence,
        model_name=primary.model_name,
        input_tokens=primary.input_tokens,
        output_tokens=primary.output_tokens,
        fallback_reason=primary.fallback_reason or supporting.fallback_reason,
        practice_set=supporting.practice_set or primary.practice_set,
        supporting_answer="\n\n---\n\n".join(
            part for part in (primary.supporting_answer, supporting.answer) if part
        ),
        tool_calls=primary.tool_calls + supporting.tool_calls,
        shared={**primary.shared, **supporting.shared},
    )
