from uuid import UUID

from app.rag.retrieval import _search_terms, _where_filter


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
