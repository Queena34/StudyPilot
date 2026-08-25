from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class StudyPlanCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    start_date: date | None = None
    duration_days: int = Field(default=7, ge=1, le=28)
    daily_minutes: int = Field(default=60, ge=15, le=480)
    include_weekends: bool = True


class StudyTaskRead(BaseModel):
    id: UUID
    scheduled_date: date
    sequence: int
    task_type: str
    topic: str
    title: str
    description: str
    estimated_minutes: int
    status: str
    completed_at: datetime | None


class StudyPlanRead(BaseModel):
    id: UUID
    course_id: UUID
    title: str
    status: str
    start_date: date
    end_date: date
    daily_minutes: int
    completion_rate: float
    created_at: datetime
    tasks: list[StudyTaskRead]


class StudyPlanList(BaseModel):
    items: list[StudyPlanRead]
    page: int
    size: int


class StudyTaskUpdate(BaseModel):
    completed: bool
