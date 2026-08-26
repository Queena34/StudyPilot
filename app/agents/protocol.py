"""Unified agent protocol required by roadmap section 4.3.

Every learning agent receives an `AgentTask` plus the shared `LearningContext`
and returns an `AgentResult`. The orchestrator records each step in an
`AgentTrace`, so a request can be explained after the fact without re-running it.
"""

from dataclasses import dataclass, field
from enum import Enum
from time import monotonic
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.agents.routing import AgentName, RoutingDecision
from app.domain.models import Message
from app.rag.types import RetrievedEvidence
from app.schemas.tutor import TutorScope


class AgentStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class LearningContext:
    """Everything an agent may read about the current learning turn."""

    user_id: UUID
    course_id: UUID
    conversation_id: UUID
    message: str
    language: str
    mode: str
    scope: TutorScope
    decision: RoutingDecision
    history: list[Message] = field(default_factory=list)
    practice_options: Any = None
    #: The only route agents have to course data, practice, grading and planning.
    tools: Any = None
    #: Academic integrity ruling for this turn, decided before any agent runs.
    integrity: Any = None
    #: Topic recovered from earlier turns, when the learner referred back to it.
    learned_topic: str | None = None
    #: Filled by the primary agent so supporting agents can build on its output.
    shared: dict[str, Any] = field(default_factory=dict)

    def history_pairs(self) -> list[tuple[str, str]]:
        return [(item.role, item.content) for item in self.history]


@dataclass(frozen=True)
class AgentTask:
    agent: AgentName
    objective: str
    inputs: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"agent": self.agent.value, "objective": self.objective}


@dataclass
class ToolCall:
    name: str
    ok: bool
    latency_ms: int
    detail: str | None = None

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "ok": self.ok,
            "latency_ms": self.latency_ms,
            "detail": self.detail,
        }


@dataclass
class AgentResult:
    """What an agent produced, plus everything the response layer needs from it."""

    answer: str
    status: AgentStatus = AgentStatus.OK
    #: Evidence status string surfaced to the learner (sufficient/partial/...).
    evidence_status: str = "general"
    evidence: list[RetrievedEvidence] = field(default_factory=list)
    model_name: str = "unknown"
    input_tokens: int | None = None
    output_tokens: int | None = None
    fallback_reason: str | None = None
    practice_set: Any = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    #: Values passed on to supporting agents in a sequential workflow.
    shared: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentStep:
    agent: AgentName
    role: str
    status: AgentStatus
    latency_ms: int
    model_name: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    fallback_reason: str | None = None
    note: str | None = None

    def as_dict(self) -> dict:
        return {
            "agent": self.agent.value,
            "role": self.role,
            "status": self.status.value,
            "latency_ms": self.latency_ms,
            "model_name": self.model_name,
            "tool_calls": [call.as_dict() for call in self.tool_calls],
            "fallback_reason": self.fallback_reason,
            "note": self.note,
        }


@dataclass
class AgentTrace:
    """One explainable record per request: route, agent order and degradations."""

    trace_id: UUID = field(default_factory=uuid4)
    route: dict = field(default_factory=dict)
    steps: list[AgentStep] = field(default_factory=list)
    total_latency_ms: int = 0

    def as_dict(self) -> dict:
        return {
            "trace_id": str(self.trace_id),
            "route": self.route,
            "steps": [step.as_dict() for step in self.steps],
            "agent_sequence": [step.agent.value for step in self.steps],
            "total_latency_ms": self.total_latency_ms,
        }


class LearningAgent(Protocol):
    """The single interface the orchestrator dispatches to."""

    name: AgentName

    async def run(self, task: AgentTask, context: LearningContext) -> AgentResult: ...


class _Timer:
    def __enter__(self) -> "_Timer":
        self._started = monotonic()
        self.elapsed_ms = 0
        return self

    def __exit__(self, *exc: object) -> None:
        self.elapsed_ms = round((monotonic() - self._started) * 1000)


def timer() -> _Timer:
    return _Timer()
