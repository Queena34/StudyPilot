from pathlib import Path

import pytest

from app.core.exceptions import AppError
from app.rag.parsers import MarkdownParser, TextParser, _chapter_heading, parser_for_suffix


def test_text_parser_cleans_utf8_text(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("第一章  概念\r\n\r\n\r\n重要内容", encoding="utf-8")

    parsed = TextParser().parse(source)

    assert parsed.pages[0].page_number == 1
    assert parsed.pages[0].text == "第一章 概念\n\n重要内容"


def test_markdown_parser_extracts_first_heading(tmp_path: Path) -> None:
    source = tmp_path / "notes.md"
    source.write_text("# Machine Learning\n\nCourse notes", encoding="utf-8")

    parsed = MarkdownParser().parse(source)

    assert parsed.pages[0].section_title == "Machine Learning"


def test_pdf_chapter_heading_detection() -> None:
    text = "Linear Models\nChapter 1. The Simple Regression Model\nCourse notes"

    assert _chapter_heading(text) == "Chapter 1. The Simple Regression Model"


def test_parser_rejects_unsupported_suffix() -> None:
    with pytest.raises(AppError) as exc_info:
        parser_for_suffix(".docx")

    assert exc_info.value.code == "UNSUPPORTED_FILE_TYPE"
