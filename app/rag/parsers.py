import re
from pathlib import Path
from typing import Protocol

from app.core.exceptions import AppError
from app.rag.types import ParsedDocument, ParsedPage


class DocumentParser(Protocol):
    def parse(self, path: Path) -> ParsedDocument: ...


class TextParser:
    def parse(self, path: Path) -> ParsedDocument:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise AppError(
                "UNSUPPORTED_TEXT_ENCODING", "文本文件必须使用UTF-8编码"
            ) from exc
        text = _clean_text(text)
        if not text:
            raise AppError("EMPTY_DOCUMENT", "文档中没有可处理的文本")
        return ParsedDocument([ParsedPage(page_number=1, text=text)])


class MarkdownParser(TextParser):
    def parse(self, path: Path) -> ParsedDocument:
        parsed = super().parse(path)
        text = parsed.pages[0].text
        heading = next(
            (match.group(1).strip() for match in re.finditer(r"^#{1,6}\s+(.+)$", text, re.M)),
            None,
        )
        return ParsedDocument([ParsedPage(page_number=1, text=text, section_title=heading)])


class PdfParser:
    def parse(self, path: Path) -> ParsedDocument:
        try:
            import fitz
        except ImportError as exc:
            raise AppError("PDF_PARSER_UNAVAILABLE", "PDF解析组件未安装") from exc

        pages: list[ParsedPage] = []
        current_section: str | None = None
        try:
            with fitz.open(path) as pdf:
                for index, page in enumerate(pdf):
                    text = _clean_text(page.get_text("text"))
                    if text:
                        current_section = _chapter_heading(text) or current_section
                        pages.append(ParsedPage(page_number=index + 1, text=text, section_title=current_section))
        except Exception as exc:
            raise AppError("PDF_PARSE_FAILED", "PDF文件解析失败") from exc
        if sum(len(page.text) for page in pages) < 20:
            raise AppError(
                "OCR_REQUIRED",
                "PDF中没有足够的可提取文本，扫描版PDF暂不支持",
            )
        return ParsedDocument(pages)


def parser_for_suffix(suffix: str) -> DocumentParser:
    parsers: dict[str, DocumentParser] = {
        ".pdf": PdfParser(),
        ".md": MarkdownParser(),
        ".txt": TextParser(),
    }
    try:
        return parsers[suffix.lower()]
    except KeyError as exc:
        raise AppError("UNSUPPORTED_FILE_TYPE", "不支持该文件类型") from exc


def _clean_text(text: str) -> str:
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _chapter_heading(text: str) -> str | None:
    match = re.search(r"(?im)^\s*((?:chapter|section|unit|module)\s+\d+\s*[.:：-]?\s*[^\n]{0,120})$", text)
    if match:
        return " ".join(match.group(1).split())
    match = re.search(r"(?m)^\s*(第\s*[一二三四五六七八九十百零〇0-9]+\s*章[^\n]{0,120})$", text)
    if match:
        return " ".join(match.group(1).split())
    for line in text.splitlines()[:12]:
        match = re.fullmatch(
            r"\s*((?:[0-9]{1,2}|[一二三四五六七八九十]+)(?:[.、:：]\s*|\s+)[A-Za-z\u3400-\u9fff][^\n]{2,100})\s*",
            line,
        )
        if match:
            return " ".join(match.group(1).split())
    return None
