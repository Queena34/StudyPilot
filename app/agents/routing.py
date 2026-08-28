"""Structured routing protocol shared by the rule router, the LLM router and callers.

`RoutingDecision` is the single contract every routing path must satisfy, so that
downstream orchestration can be added without changing the router surface again.
"""

from dataclasses import dataclass, field
from enum import Enum
from uuid import UUID


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
    EVALUATE = "evaluate"
    GENERAL = "general"
    CLARIFY = "clarify"


class AgentName(str, Enum):
    TUTOR = "tutor"
    QUIZ = "quiz"
    EVALUATOR = "evaluator"
    PLANNER = "planner"
    PROGRESS = "progress"
    CATALOG = "catalog"
    GENERAL = "general"


class ExecutionMode(str, Enum):
    SINGLE = "single"
    SEQUENTIAL = "sequential"
    CLARIFY = "clarify"


class RoutingSource(str, Enum):
    RULE = "rule"
    LLM = "llm"
    LLM_UNAVAILABLE = "llm_unavailable"
    LLM_FAILED = "llm_failed"
    LLM_REJECTED = "llm_rejected"


#: Below this rule confidence the hybrid router asks the LLM router for help.
RULE_CONFIDENCE_THRESHOLD = 0.80

#: Below this final confidence the router asks the learner to clarify.
CLARIFICATION_THRESHOLD = 0.45

INTENT_TARGETS: dict[LearningIntent, RouteTarget] = {
    LearningIntent.COURSE_QA: RouteTarget.RAG,
    LearningIntent.CONCEPT_EXPLANATION: RouteTarget.RAG,
    LearningIntent.PRACTICE_GENERATION: RouteTarget.PRACTICE,
    LearningIntent.ANSWER_EVALUATION: RouteTarget.EVALUATE,
    LearningIntent.STUDY_PLANNING: RouteTarget.STUDY_PLAN,
    LearningIntent.PROGRESS_REVIEW: RouteTarget.PROGRESS,
    LearningIntent.DOCUMENT_MANAGEMENT: RouteTarget.COURSE_CATALOG,
    LearningIntent.GENERAL: RouteTarget.GENERAL,
}

INTENT_AGENTS: dict[LearningIntent, AgentName] = {
    LearningIntent.COURSE_QA: AgentName.TUTOR,
    LearningIntent.CONCEPT_EXPLANATION: AgentName.TUTOR,
    LearningIntent.PRACTICE_GENERATION: AgentName.QUIZ,
    LearningIntent.ANSWER_EVALUATION: AgentName.EVALUATOR,
    LearningIntent.STUDY_PLANNING: AgentName.PLANNER,
    LearningIntent.PROGRESS_REVIEW: AgentName.PROGRESS,
    LearningIntent.DOCUMENT_MANAGEMENT: AgentName.CATALOG,
    LearningIntent.GENERAL: AgentName.GENERAL,
}


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
    #: Optional, like the page range: absent means the whole scope applies.
    section: int | None = None
    #: Language the material is written in, and the query rewritten into it.
    #: Retrieval uses `retrieval_query`; `standalone_query` stays as the learner
    #: wrote it, for anything shown back to them.
    material_language: str = "en"
    retrieval_query: str = ""

    @property
    def search_query(self) -> str:
        return self.retrieval_query or self.standalone_query

    def as_dict(self) -> dict:
        return {
            "standalone_query": self.standalone_query,
            "retrieval_query": self.search_query,
            "material_language": self.material_language,
            "course_id": str(self.course_id),
            "document_types": self.document_types,
            "document_ids": [str(value) for value in self.document_ids],
            "page_from": self.page_from,
            "page_to": self.page_to,
            "section": self.section,
            "requested_language": self.requested_language,
            "top_k": self.top_k,
        }


@dataclass(frozen=True)
class RoutingDecision:
    """The structured routing contract required by the agent architecture roadmap."""

    intent: LearningIntent
    primary_agent: AgentName
    supporting_agents: list[AgentName]
    execution_mode: ExecutionMode
    confidence: float
    reason: str
    query_plan: QueryPlan
    source: RoutingSource = RoutingSource.RULE
    rule_confidence: float | None = None
    clarification: str | None = None
    #: Route target kept for the current TutorService dispatch; the orchestrator
    #: introduced in roadmap step 2 will dispatch on `primary_agent` instead.
    target: RouteTarget = RouteTarget.RAG

    def as_dict(self) -> dict:
        return {
            "intent": self.intent.value,
            "primary_agent": self.primary_agent.value,
            "supporting_agents": [agent.value for agent in self.supporting_agents],
            "execution_mode": self.execution_mode.value,
            "confidence": round(self.confidence, 4),
            "reason": self.reason,
            "source": self.source.value,
            "rule_confidence": self.rule_confidence,
            "clarification": self.clarification,
            "target": self.target.value,
            "query_plan": self.query_plan.as_dict(),
        }


def decision_for(
    intent: LearningIntent,
    *,
    confidence: float,
    reason: str,
    query_plan: QueryPlan,
    source: RoutingSource = RoutingSource.RULE,
    supporting_agents: list[AgentName] | None = None,
    rule_confidence: float | None = None,
) -> RoutingDecision:
    """Build a decision with the intent's canonical target and agent mapping."""

    supporting = supporting_agents or []
    return RoutingDecision(
        intent=intent,
        primary_agent=INTENT_AGENTS[intent],
        supporting_agents=supporting,
        execution_mode=ExecutionMode.SEQUENTIAL if supporting else ExecutionMode.SINGLE,
        confidence=confidence,
        reason=reason,
        query_plan=query_plan,
        source=source,
        rule_confidence=rule_confidence,
        target=INTENT_TARGETS[intent],
    )
