from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CourseFields(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    course_code: str | None = Field(default=None, max_length=80)
    institution: str | None = Field(default=None, max_length=200)
    semester: str | None = Field(default=None, max_length=80)
    exam_date: date | None = None
    target_grade: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=5000)

    @field_validator("name", mode="before")
    @classmethod
    def strip_required_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("course_code", "institution", "semester", "target_grade", mode="before")
    @classmethod
    def strip_optional_text(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class CourseCreate(CourseFields):
    pass


class CourseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    course_code: str | None = Field(default=None, max_length=80)
    institution: str | None = Field(default=None, max_length=200)
    semester: str | None = Field(default=None, max_length=80)
    exam_date: date | None = None
    target_grade: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=5000)

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("课程名称不能为空")
        return value


class CourseRead(CourseFields):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class CourseList(BaseModel):
    items: list[CourseRead]
    page: int
    size: int
    total: int
