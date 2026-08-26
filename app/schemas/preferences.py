from pydantic import BaseModel, Field

from app.schemas.practice import Difficulty, QuestionType
from app.schemas.tutor import ExplanationMode, ResponseLanguage


class UserPreferencesRead(BaseModel):
    """The learner's own defaults. PRD 8.6 requires these be visible and editable."""

    explanation_language: ResponseLanguage
    answer_language: ResponseLanguage
    explanation_style: ExplanationMode
    default_question_type: QuestionType
    default_difficulty: Difficulty
    default_question_count: int
    include_language_feedback: bool


class UserPreferencesUpdate(BaseModel):
    explanation_language: ResponseLanguage | None = None
    answer_language: ResponseLanguage | None = None
    explanation_style: ExplanationMode | None = None
    default_question_type: QuestionType | None = None
    default_difficulty: Difficulty | None = None
    default_question_count: int | None = Field(default=None, ge=1, le=10)
    include_language_feedback: bool | None = None
