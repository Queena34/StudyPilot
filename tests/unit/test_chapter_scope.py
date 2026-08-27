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


class _RefiningLLM:
    """An LLM router that rewrites the query, as it does for unclear messages."""

    def __init__(self, refined: str) -> None:
        self.refined = refined

    async def propose(self, *, message, history=None):
        from app.agents.llm_router import LLMRoutingProposal
        from app.agents.routing import LearningIntent as _Intent

        return LLMRoutingProposal(
            intent=_Intent.COURSE_QA, confidence=0.9, reason="t", standalone_query=self.refined
        )


class _RecordingTranslator:
    def __init__(self) -> None:
        self.seen: list[str] = []

    async def to_material_language(self, query, material_language):
        self.seen.append(query)
        return f"[{material_language}] {query}"


async def _routed(message: str, scope: TutorScope | None = None):
    translator = _RecordingTranslator()
    decision = await LearningIntentRouter(
        llm_router=_RefiningLLM("refined query"), translator=translator
    ).route(
        message=message,
        standalone_query=message,
        course_id=COURSE_ID,
        language="zh",
        scope=scope or TutorScope(),
        material_language="en",
    )
    return decision, translator


async def test_an_llm_refinement_keeps_the_chapter() -> None:
    # Rebuilding the plan field by field used to drop everything not listed.
    decision, _ = await _routed("随便讲讲第一章")

    assert decision.source.value == "llm"
    assert decision.query_plan.chapter == 1


async def test_an_llm_refinement_keeps_the_learner_scope() -> None:
    document_id = uuid4()
    decision, _ = await _routed("随便讲讲", TutorScope(document_ids=[document_id], page_from=3))

    assert decision.query_plan.document_ids == [document_id]
    assert decision.query_plan.page_from == 3
    assert decision.query_plan.material_language == "en"


async def test_the_refined_query_is_the_one_translated() -> None:
    decision, translator = await _routed("随便讲讲")

    # Translating before the refinement meant the refinement went out untranslated.
    assert translator.seen == ["refined query"]
    assert decision.query_plan.retrieval_query == "[en] refined query"
    assert decision.query_plan.search_query == "[en] refined query"


async def test_a_rule_settled_turn_is_still_translated() -> None:
    decision, translator = await _routed("我现在有什么课程资料？")

    # Catalog answers do not retrieve, so nothing is translated for them.
    assert decision.source.value == "rule"
    assert translator.seen == []
