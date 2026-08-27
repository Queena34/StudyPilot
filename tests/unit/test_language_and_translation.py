import pytest

from app.agents.query_translation import QueryTranslationGateway
from app.rag.language import detect_language, dominant_language


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("what is a residual", "en"),
        ("The simple linear model: E[Y|X] = beta_0 + beta_1 x", "en"),
        ("ANOVA", "en"),
        ("解释一下什么是残差", "zh"),
        # Technical Chinese carries English terms; that must not flip it to English.
        ("残差 residual 和误差 error term 的区别", "zh"),
        ("", "en"),
    ],
)
def test_language_is_detected_from_character_mix(text, expected) -> None:
    assert detect_language(text) == expected


def test_a_stray_chinese_note_does_not_flip_an_english_deck() -> None:
    pages = ["English lecture content. " * 80, "这是一页中文批注"]

    assert dominant_language(pages) == "en"


def test_a_chinese_document_is_recognised() -> None:
    assert dominant_language(["这是一份中文讲义，讲的是线性回归模型的基本假设。" * 20]) == "zh"


def test_no_material_defaults_to_english() -> None:
    assert dominant_language([]) == "en"


async def test_a_query_already_in_the_material_language_is_left_alone() -> None:
    gateway = QueryTranslationGateway()

    # No model call is made, so this holds with or without an API key.
    assert await gateway.to_material_language("what is a residual", "en") == "what is a residual"
    assert await gateway.to_material_language("什么是残差", "zh") == "什么是残差"


async def test_an_unknown_material_language_leaves_the_query_alone() -> None:
    assert await QueryTranslationGateway().to_material_language("什么是残差", "fr") == "什么是残差"
