from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.agents.intent_router import LearningIntentRouter
from app.schemas.tutor import TutorScope
from app.services.tutor_service import (
    _mentions_document_reference,
    _resolve_document_references,
)


COURSE_ID = UUID("00000000-0000-0000-0000-000000000010")


def _plan(message: str, scope: TutorScope | None = None):
    return LearningIntentRouter().analyze(
        message=message,
        standalone_query=message,
        course_id=COURSE_ID,
        language="zh",
        scope=scope or TutorScope(),
    ).query_plan


@pytest.mark.parametrize(
    ("message", "chapter"),
    [
        ("根据第一章内容出3道练习题", 1),
        ("第二章讲了什么", 2),
        ("chapter 3 的重点是什么", 3),
        ("根据资料第一章，最小二乘法的目标是什么？", 1),
        ("解释一下残差", None),
        ("出3道练习题", None),
    ],
)
def test_the_router_resolves_the_chapter_into_the_plan(message, chapter) -> None:
    # Scope belongs in the QueryPlan; nothing downstream re-reads the message.
    assert _plan(message).chapter == chapter


def test_an_explicitly_chosen_chapter_outranks_the_message() -> None:
    plan = _plan("根据第二章出题", TutorScope(chapter=5))

    # The learner's explicit selection is never overridden by parsing.
    assert plan.chapter == 5


def test_the_plan_carries_the_chapter_alongside_the_other_scope() -> None:
    document_id = uuid4()
    plan = _plan(
        "根据第一章出题",
        TutorScope(document_ids=[document_id], page_from=2, page_to=9),
    )

    assert plan.chapter == 1
    assert plan.document_ids == [document_id]
    assert plan.page_from == 2 and plan.page_to == 9


def test_the_plan_serializes_the_chapter() -> None:
    assert _plan("根据第一章出题").as_dict()["chapter"] == 1


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        # "资料第一章" is a chapter of the materials, not the first material.
        ("根据资料第一章，最小二乘法的目标是什么？", False),
        ("资料第3页说了什么", False),
        ("根据第一章出题", False),
        ("资料1里讲了什么", True),
        ("根据第二份资料", True),
        ("讲讲 notes.pdf", True),
    ],
)
def test_a_chapter_is_not_mistaken_for_a_material_ordinal(message, expected) -> None:
    assert _mentions_document_reference(message) is expected


def test_resolution_ignores_a_chapter_number_when_picking_a_document() -> None:
    documents = [
        SimpleNamespace(id=uuid4(), filename="second.pdf"),
        SimpleNamespace(id=uuid4(), filename="first.pdf"),
    ]

    assert _resolve_document_references("根据资料第一章出题", documents) == []
    # An ordinal that really does name a material still resolves.
    assert _resolve_document_references("资料1讲了什么", documents) == [documents[-1].id]
