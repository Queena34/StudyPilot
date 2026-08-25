from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class TopicMasteryRead(BaseModel):
    topic: str
    status: str
    mastery_score: float
    average_score: float
    recent_score: float
    attempt_count: int
    common_errors: dict[str, int]
    last_practiced_at: datetime | None


class CourseProgressRead(BaseModel):
    course_id: UUID
    overall_mastery: float
    practiced_topics: int
    total_attempts: int
    weak_topics: int
    learning_topics: int
    mastered_topics: int


class RecommendationRead(BaseModel):
    topic: str
    mastery_score: float
    priority: int
    reason: str
    suggested_action: str


class RecommendationList(BaseModel):
    items: list[RecommendationRead]
