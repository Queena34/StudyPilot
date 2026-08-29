from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.tutor import Citation, ResponseLanguage, TutorScope


class QuestionType(str, Enum):
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    SHORT_ANSWER = "short_answer"
    CONCEPT = "concept"


class Difficulty(str, Enum):
    BASIC = "basic"
    MEDIUM = "medium"
    ADVANCED = "advanced"


class PracticeSetCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    topic: str | None = Field(default=None, max_length=300)
    question_type: QuestionType = QuestionType.SHORT_ANSWER
    difficulty: Difficulty = Difficulty.MEDIUM
    question_count: int = Field(default=3, ge=1, le=10)
    language: ResponseLanguage = ResponseLanguage.ZH
    prioritize_weak_topics: bool = False
    scope: TutorScope = Field(default_factory=TutorScope)


class QuestionOption(BaseModel):
    id: str
    text: str


class PracticeQuestionRead(BaseModel):
    id: UUID
    question_type: QuestionType
    difficulty: Difficulty
    content: str
    options: list[QuestionOption] | None
    knowledge_points: list[str]
    sources: list[Citation]


class PracticeSetRead(BaseModel):
    id: UUID
    course_id: UUID
    title: str
    status: str
    configuration: dict
    model_name: str
    created_at: datetime
    completed_at: datetime | None
    questions: list[PracticeQuestionRead]


class PracticeSetSummary(BaseModel):
    """One row of the course practice history, without leaking any answers."""

    id: UUID
    title: str
    status: str
    question_type: QuestionType
    difficulty: Difficulty
    topic: str | None
    question_count: int
    answered_count: int
    incorrect_count: int
    average_score: float | None
    created_at: datetime


class PracticeSetList(BaseModel):
    items: list[PracticeSetSummary]
    page: int
    size: int


class GeneratedOption(BaseModel):
    id: str
    text: str
    is_correct: bool


class RubricItem(BaseModel):
    criterion: str
    weight: float = Field(gt=0, le=1)
    required_concepts: list[str]
    evidence_ids: list[str]


class GeneratedQuestion(BaseModel):
    question_type: QuestionType
    difficulty: Difficulty
    content: str = Field(min_length=5)
    options: list[GeneratedOption] | None = None
    knowledge_points: list[str] = Field(min_length=1)
    reference_answer: str = Field(min_length=1)
    rubric: list[RubricItem] = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
