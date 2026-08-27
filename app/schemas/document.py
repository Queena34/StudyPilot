from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentType(str, Enum):
    LECTURE = "lecture"
    READING = "reading"
    ASSIGNMENT = "assignment"
    PAST_EXAM = "past_exam"
    NOTES = "notes"
    OTHER = "other"


class JobSummary(BaseModel):
    id: UUID
    status: str
    progress: int


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    course_id: UUID
    filename: str
    mime_type: str
    document_type: str
    status: str
    size_bytes: int
    language: str = "en"
    page_count: int | None
    chunk_count: int
    error_code: str | None
    error_message: str | None
    created_at: datetime
    job: JobSummary | None = None


class DocumentList(BaseModel):
    items: list[DocumentRead]
    page: int
    size: int

