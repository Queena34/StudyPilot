from types import SimpleNamespace

import pytest

from app.agents.presenters import CITATION_SNIPPET_LIMIT, _clean_topic, _practice_configuration
from app.schemas.practice import QuestionType
from app.schemas.tutor import ResponseLanguage, TutorPracticeOptions, TutorScope


@pytest.mark.parametrize(
    ("captured", "expected"),
    [
        ("残差的简答题", "残差"),
        ("残差", "残差"),
        ("ANOVA 的3道选择题", "ANOVA"),
        ("假设检验的概念解释题", "假设检验"),
        ("多重共线性的练习", "多重共线性"),
        ("residuals short-answer questions", "residuals"),
        ("leverage points quiz", "leverage points"),
    ],
)
def test_topic_keeps_the_subject_and_drops_the_request_wording(captured, expected) -> None:
    assert _clean_topic(captured) == expected


def test_topic_that_is_only_request_wording_becomes_none() -> None:
    # Better no topic than a topic the material cannot possibly support.
    assert _clean_topic("简答题") is None
    assert _clean_topic("") is None


def test_asking_about_a_concept_does_not_make_the_question_form_the_topic() -> None:
    configuration = _practice_configuration(
        "给我出1道关于残差的简答题", ResponseLanguage.ZH, TutorScope()
    )

    assert configuration.topic == "残差"
    assert configuration.question_type == QuestionType.SHORT_ANSWER


def test_practice_language_defaults_to_the_conversation_language() -> None:
    configuration = _practice_configuration("出3道题", ResponseLanguage.ZH, TutorScope())

    assert configuration.language == ResponseLanguage.ZH


def test_an_explicit_practice_language_outranks_the_conversation_language() -> None:
    options = TutorPracticeOptions(question_count=3, language=ResponseLanguage.EN)

    configuration = _practice_configuration(
        "出3道题", ResponseLanguage.ZH, TutorScope(), options=options
    )

    # Taught in one language, examined in another: the exam language wins.
    assert configuration.language == ResponseLanguage.EN


def test_options_without_a_language_still_fall_back() -> None:
    options = TutorPracticeOptions(question_count=3)

    configuration = _practice_configuration(
        "出3道题", ResponseLanguage.ZH_EN, TutorScope(), options=options
    )

    assert configuration.language == ResponseLanguage.ZH_EN


def test_citation_snippets_carry_the_whole_passage() -> None:
    # 300 characters routinely cut off the sentence that supported the claim.
    assert CITATION_SNIPPET_LIMIT >= 3200
