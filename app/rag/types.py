from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedPage:
    page_number: int
    text: str
    section_title: str | None = None


@dataclass(frozen=True)
class ParsedDocument:
    pages: list[ParsedPage]


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int
    page_number: int
    text: str
    section_title: str | None = None


@dataclass(frozen=True)
class RetrievedEvidence:
    chunk_id: str
    document_id: str
    filename: str
    page_number: int
    section_title: str | None
    text: str
    score: float
