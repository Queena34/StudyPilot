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


def test_numbered_heading_is_a_chapter_marker() -> None:
    from app.rag.retrieval import _chapter_marker

    assert _chapter_marker("1 Introduction\nLearning goals") == (1, "1 Introduction")
    assert _chapter_marker("Body", "Section 2. Estimation") == (2, "Chapter 2. Estimation")


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
