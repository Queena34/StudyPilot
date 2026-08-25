import re

from app.rag.types import ParsedDocument, TextChunk


class TextChunker:
    def __init__(self, max_chars: int = 3200, overlap_chars: int = 400) -> None:
        if max_chars <= 0 or overlap_chars < 0 or overlap_chars >= max_chars:
            raise ValueError("invalid chunk size configuration")
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars

    def split(self, document: ParsedDocument) -> list[TextChunk]:
        chunks: list[TextChunk] = []
        index = 0
        for page in document.pages:
            section = page.section_title
            paragraphs = [part.strip() for part in re.split(r"\n\s*\n", page.text) if part.strip()]
            buffer = ""
            for paragraph in paragraphs:
                heading = re.match(r"^#{1,6}\s+(.+)$", paragraph)
                if heading:
                    section = heading.group(1).strip()
                if len(paragraph) > self.max_chars:
                    if buffer:
                        chunks.append(TextChunk(index, page.page_number, buffer, section))
                        index += 1
                        buffer = ""
                    for piece in self._window(paragraph):
                        chunks.append(TextChunk(index, page.page_number, piece, section))
                        index += 1
                    continue
                candidate = f"{buffer}\n\n{paragraph}".strip() if buffer else paragraph
                if len(candidate) <= self.max_chars:
                    buffer = candidate
                    continue
                chunks.append(TextChunk(index, page.page_number, buffer, section))
                index += 1
                overlap_space = max(0, self.max_chars - len(paragraph) - 2)
                overlap_size = min(self.overlap_chars, overlap_space)
                overlap = buffer[-overlap_size:] if overlap_size else ""
                buffer = f"{overlap}\n\n{paragraph}".strip()
            if buffer:
                chunks.append(TextChunk(index, page.page_number, buffer, section))
                index += 1
        return chunks

    def _window(self, text: str) -> list[str]:
        step = self.max_chars - self.overlap_chars
        return [text[start : start + self.max_chars] for start in range(0, len(text), step)]
