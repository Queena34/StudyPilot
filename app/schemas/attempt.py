from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.tutor import Citation


class AttemptCreate(BaseModel):
    answer: str = Field(min_length=1, max_length=12_000)
    include_language_feedback: bool = False


class CriterionEvaluation(BaseModel):
    criterion_index: int = Field(ge=0)
    earned_ratio: float = Field(ge=0, le=1)
    reason: str
    evidence_ids: list[str]


class CriterionResult(CriterionEvaluation):
    criterion: str
    weight: float
    points: float


class EvaluationFeedback(BaseModel):
    summary: str
    covered_concepts: list[str]
    missing_concepts: list[str]
    knowledge_errors: list[str]
    language_feedback: list[str]
    recommended_topics: list[str]


class AttemptRead(BaseModel):
    id: UUID
    question_id: UUID
    answer: str
    score: float
    max_score: int = 100
    criterion_results: list[CriterionResult]
    feedback: EvaluationFeedback
    reference_answer: str
    sources: list[Citation]
    evaluation_model: str
    created_at: datetime


class AttemptList(BaseModel):
    items: list[AttemptRead]
    page: int
    size: int
