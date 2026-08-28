import pytest
from uuid import UUID

from app.rag.retrieval import _chapter_evidence, _chapter_number, _search_terms, _where_filter


def test_where_filter_always_enforces_user_and_course() -> None:
    user_id = UUID("00000000-0000-0000-0000-000000000001")
    course_id = UUID("00000000-0000-0000-0000-000000000002")
    document_id = UUID("00000000-0000-0000-0000-000000000003")

    where = _where_filter(
        user_id=user_id,
        course_id=course_id,
        document_types=["lecture"],
        document_ids=[document_id],
        page_from=2,
        page_to=5,
    )

    assert {"user_id": str(user_id)} in where["$and"]
    assert {"course_id": str(course_id)} in where["$and"]
    assert {"document_type": {"$in": ["lecture"]}} in where["$and"]
    assert {"page_number": {"$gte": 2}} in where["$and"]


def test_search_terms_support_chinese_and_english() -> None:
    terms = _search_terms("解释 L1 regularization 正则化")

    assert {"l1", "regularization", "正", "则", "化"} <= terms


def test_chapter_number_supports_chinese_and_english() -> None:
    assert _chapter_number("请讲解第一章") == 1
    assert _chapter_number("summarize Chapter 12") == 12


def test_an_explicit_chapter_marker_is_read() -> None:
    from app.rag.retrieval import _chapter_marker

    assert _chapter_marker("Body", "Section 2. Estimation") == (2, "Chapter 2. Estimation")
    assert _chapter_marker("Chapter 3. Inference\nBody")[0] == 3
    # A numbered heading with no "Chapter" word is not read by the strict form.
    assert _chapter_marker("1 Introduction\nLearning goals") is None


@pytest.mark.parametrize(
    "line",
    [
        "2 Pints",                        # a factor level in an alcohol study
        "2 Pints.Male",
        "4 Pints:Female−2 Pints:Female",  # a contrast label
        "27 obs. of",                     # R output
        "92 Mutual",
        "3 Male",
        "1 / 53",                         # a slide footer
    ],
)
def test_data_lines_are_not_read_as_headings(line) -> None:
    """A statistics handout is full of lines shaped like numbered headings.

    Reading them as chapters buried a real chapter's 13 passages under 180 rows
    of an alcohol experiment.
    """
    from app.rag.retrieval import _loose_chapter_marker

    assert _loose_chapter_marker(line) is None


@pytest.mark.parametrize(
    ("line", "number"),
    [
        ("2 The General Linear Model", 2),
        ("1 Introduction to ANOVA", 1),
        ("12 Model diagnostics", 12),
        ("3 一般线性模型", 3),
    ],
)
def test_real_numbered_headings_are_still_read(line, number) -> None:
    from app.rag.retrieval import _loose_chapter_marker

    assert _loose_chapter_marker(line) == (number, line)


def test_the_loose_form_never_supplements_an_explicit_one() -> None:
    """A document that says "Chapter" is read only that way.

    Mixing the two let noise outnumber the real headings in the same document.
    """
    from app.rag.retrieval import _chapter_evidence

    documents = ["Chapter 1. Simple Regression\nbody", "2 Pints", "more chapter one text"]
    payload = {
        "ids": [f"doc:{i}" for i in range(3)],
        "documents": documents,
        "metadatas": [
            {"document_id": "doc", "source_file": "notes.pdf", "page_number": i + 1, "chunk_index": i}
            for i in range(3)
        ],
    }

    evidence = _chapter_evidence(payload, 1, 8)

    # "2 Pints" must not close chapter one.
    assert [item.page_number for item in evidence] == [1, 2, 3]


def test_a_one_off_lookalike_does_not_become_a_chapter() -> None:
    """A real chapter opens a run of passages; a stray line appears once."""
    from app.rag.retrieval import _chapter_evidence

    payload = {
        "ids": [f"doc:{i}" for i in range(3)],
        "documents": ["intro text", "20 days faster", "closing text"],
        "metadatas": [
            {"document_id": "doc", "source_file": "anova.pdf", "page_number": i + 1, "chunk_index": i}
            for i in range(3)
        ],
    }

    evidence = _chapter_evidence(payload, 1, 8)

    assert all(item.section_title == "第一部分（原文未标注章节）" for item in evidence)


def test_chapter_evidence_stops_at_next_chapter() -> None:
    payload = {
        "ids": ["doc:0", "doc:1", "doc:2", "doc:3"],
        "documents": [
            "Chapter 0. Introduction\nOverview",
            "Chapter 1. Simple Regression\nDefinition",
            "Slope and intercept",
            "Chapter 2. Multiple Regression\nDefinition",
        ],
        "metadatas": [
            {"document_id": "doc", "source_file": "lecture.pdf", "page_number": index + 1, "chunk_index": index}
            for index in range(4)
        ],
    }

    evidence = _chapter_evidence(payload, 1, 8)

    assert [item.page_number for item in evidence] == [2, 3]
    assert all(item.section_title == "Chapter 1. Simple Regression" for item in evidence)


def test_first_chapter_uses_whole_document_when_source_has_no_chapter_markers() -> None:
    payload = {
        "ids": ["doc:0", "doc:1", "doc:2"],
        "documents": ["One-way ANOVA", "F test assumptions", "Post-hoc comparisons"],
        "metadatas": [
            {"document_id": "doc", "source_file": "anova.pdf", "page_number": index + 1, "chunk_index": index}
            for index in range(3)
        ],
    }

    evidence = _chapter_evidence(payload, 1, 8)

    assert [item.page_number for item in evidence] == [1, 2, 3]
    assert all(item.section_title == "第一部分（原文未标注章节）" for item in evidence)
