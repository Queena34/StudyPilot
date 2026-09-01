"""Asking for a chapter the material does not have is not a retrieval failure.

"第二十章" against an eight-part handout means the learner named a range that
does not exist. Reporting that as "no evidence found" sends them looking for a
problem that is not there, when the parts were detected at ingestion and can
simply be listed.
"""

from types import SimpleNamespace

from app.agents.presenters import missing_section_answer


def _document(filename: str, sections: list[dict]):
    return SimpleNamespace(filename=filename, sections_json=sections)


ANOVA = _document(
    "ANOVA.pdf",
    [
        {"index": 1, "title": "One-way ANOVA: F-test"},
        {"index": 2, "title": "Factor levels"},
        {"index": 3, "title": "Diagnostics"},
    ],
)


def test_an_out_of_range_chapter_names_what_the_material_has() -> None:
    answer = missing_section_answer(20, [ANOVA], "zh")

    assert answer is not None
    assert "没有第 20 章" in answer
    assert "共 3 个部分" in answer
    assert "编号 1–3" in answer
    assert "One-way ANOVA: F-test" in answer


def test_a_chapter_that_exists_is_left_to_normal_retrieval() -> None:
    """Returning None keeps the ordinary answer path; this is only for the gap."""

    assert missing_section_answer(2, [ANOVA], "zh") is None


def test_material_with_no_detected_structure_says_so() -> None:
    plain = _document("notes.pdf", [{"index": 1, "title": "全文"}])

    answer = missing_section_answer(3, [plain], "zh")

    assert answer is not None
    assert "未能识别出章节结构" in answer


def test_one_document_having_the_chapter_is_enough() -> None:
    """Scoped to several documents, only a gap in all of them is a gap."""

    other = _document("book.pdf", [{"index": 20, "title": "Chapter 20"}])

    assert missing_section_answer(20, [ANOVA, other], "zh") is None


def test_english_answers_in_english() -> None:
    answer = missing_section_answer(20, [ANOVA], "en")

    assert answer is not None
    assert "has no part 20" in answer
    assert "3 part(s)" in answer


def test_no_documents_in_scope_falls_back_to_the_ordinary_message() -> None:
    assert missing_section_answer(3, [], "zh") is None
