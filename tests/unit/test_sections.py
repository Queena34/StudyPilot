"""Section detection across the ways material expresses its own structure."""

from app.rag.sections import Section, detect_sections, section_for_page
from app.rag.types import ParsedDocument, ParsedPage


def _document(*pages: str) -> ParsedDocument:
    return ParsedDocument([
        ParsedPage(page_number=index, text=text) for index, text in enumerate(pages, start=1)
    ])


def test_numbered_chapters_are_detected() -> None:
    document = _document(
        "Chapter 1. The Simple Regression\nbody",
        "more chapter one",
        "Chapter 2. The General Linear Model\nbody",
    )

    sections = detect_sections(document)

    assert [(s.index, s.title, s.page_from, s.page_to) for s in sections] == [
        (1, "Chapter 1. The Simple Regression", 1, 2),
        (2, "Chapter 2. The General Linear Model", 3, 3),
    ]


def test_chinese_chapters_are_detected() -> None:
    document = _document("第一章 简单回归\n正文", "第二章 一般线性模型\n正文")

    assert [s.index for s in detect_sections(document)] == [1, 2]


def test_a_slide_deck_is_split_by_its_title_slides() -> None:
    """A handout with no numbering at all still has parts.

    Modelling structure as a number left this material with none, so a learner
    could not ask about it by chapter.
    """

    document = _document(
        "One-way ANOVA: F-test\nAriel Alonso Abad\nCatholic University of Leuven\nslide body",
        "more of the first deck",
        "Two-way ANOVA: Equal sample size\nAriel Alonso Abad\nCatholic University of Leuven\nbody",
    )

    sections = detect_sections(document)

    assert [s.title for s in sections] == [
        "One-way ANOVA: F-test",
        "Two-way ANOVA: Equal sample size",
    ]
    assert sections[0].page_to == 2


def test_a_single_affiliation_is_not_a_boundary() -> None:
    # One occurrence is a cover page, not a repeating deck pattern.
    document = _document(
        "Course notes\nAriel Alonso Abad\nCatholic University of Leuven",
        "body",
        "more body",
    )

    assert [s.title for s in detect_sections(document)] == ["全文"]


def test_markdown_headings_become_sections() -> None:
    document = _document("# 第一部分\n正文\n\n## 第二部分\n正文")

    assert [s.title for s in detect_sections(document)] == ["第一部分", "第二部分"]


def test_material_without_structure_is_one_section_rather_than_a_guess() -> None:
    """Inventing structure is what buried a real chapter under an experiment."""

    document = _document("2 Pints", "27 obs. of", "4 Pints:Female−2 Pints:Female")

    sections = detect_sections(document)

    assert len(sections) == 1
    assert sections[0].title == "全文"
    assert (sections[0].page_from, sections[0].page_to) == (1, 3)


def test_explicit_chapters_win_over_a_slide_pattern() -> None:
    document = _document(
        "Chapter 1. Intro\nAriel Alonso Abad\nCatholic University of Leuven",
        "Chapter 2. Next\nAriel Alonso Abad\nCatholic University of Leuven",
    )

    assert [s.title for s in detect_sections(document)] == ["Chapter 1. Intro", "Chapter 2. Next"]


def test_a_page_maps_to_the_section_containing_it() -> None:
    sections = [Section(1, "A", 1, 4), Section(2, "B", 5, 9)]

    assert section_for_page(sections, 4).title == "A"
    assert section_for_page(sections, 5).title == "B"
    assert section_for_page(sections, 99) is None
    assert section_for_page([], 1) is None


def test_an_empty_document_has_no_sections() -> None:
    assert detect_sections(ParsedDocument([])) == []


def test_a_book_opening_on_chapter_zero_keeps_the_numbers_it_states() -> None:
    """"第一章" must reach Chapter 1, not the first section in page order."""

    document = _document(
        "Chapter 0. Introduction\nwhy regression",
        "Chapter 1. The Simple Regression\nthe model",
        "Chapter 2. Inference\nconfidence intervals",
    )

    sections = detect_sections(document)

    assert [(section.index, section.title) for section in sections] == [
        (0, "Chapter 0. Introduction"),
        (1, "Chapter 1. The Simple Regression"),
        (2, "Chapter 2. Inference"),
    ]


def test_unnumbered_parts_fall_back_to_their_position() -> None:
    document = _document(
        "One-way ANOVA: F-test\nBart Michiels\nKU Leuven University",
        "contrast estimation",
        "Two-way ANOVA\nBart Michiels\nKU Leuven University",
        "interaction",
    )

    sections = detect_sections(document)

    assert [section.index for section in sections] == [1, 2]
