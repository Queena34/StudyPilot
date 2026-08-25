from enum import Enum
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.document import DocumentType


class ResponseLanguage(str, Enum):
    ZH = "zh"
    EN = "en"
    ZH_EN = "zh-en"


class ExplanationMode(str, Enum):
    CONCISE = "concise"
    DEEP = "deep"
    SOCRATIC = "socratic"


class TutorScope(BaseModel):
    document_types: list[DocumentType] = Field(default_factory=list, max_length=6)
    document_ids: list[UUID] = Field(default_factory=list, max_length=50)
    page_from: int | None = Field(default=None, ge=1)
    page_to: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_page_range(self) -> "TutorScope":
        if self.page_from and self.page_to and self.page_from > self.page_to:
            raise ValueError("page_from不能大于page_to")
        return self


class TutorMessageCreate(BaseModel):
    conversation_id: UUID | None = None
    message: str = Field(min_length=2, max_length=4000)
    response_language: ResponseLanguage = ResponseLanguage.ZH
    mode: ExplanationMode = ExplanationMode.DEEP
    scope: TutorScope = Field(default_factory=TutorScope)


class Citation(BaseModel):
    citation_id: str
    document_id: UUID
    filename: str
    page_number: int
    section_title: str | None
    snippet: str
    chunk_id: str
    score: float


class TokenUsage(BaseModel):
    model_name: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class TutorMessageRead(BaseModel):
    message_id: UUID
    conversation_id: UUID
    answer: str
    citations: list[Citation]
    evidence_status: str
    suggested_followups: list[str]
    usage: TokenUsage


class ConversationRead(BaseModel):
    id: UUID
    course_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationList(BaseModel):
    items: list[ConversationRead]
    page: int
    size: int


class StoredMessageRead(BaseModel):
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    citations: list[Citation]
    model_name: str | None
    latency_ms: int | None
    created_at: datetime


class MessageList(BaseModel):
    items: list[StoredMessageRead]
    page: int
    size: int
