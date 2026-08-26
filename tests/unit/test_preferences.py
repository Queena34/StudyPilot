from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.exceptions import ResourceNotFoundError
from app.schemas.preferences import UserPreferencesUpdate
from app.services.preferences_service import PreferencesService, _to_read


def _user(**overrides):
    defaults = dict(
        explanation_language="zh",
        answer_language="en",
        explanation_style="deep",
        default_question_type="single_choice",
        default_difficulty="medium",
        default_question_count=5,
        include_language_feedback=False,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class _Repository:
    def __init__(self, user=None) -> None:
        self.user = user
        self.saved = None

    async def get(self, user_id):
        return self.user

    async def save(self, user):
        self.saved = user
        return user


async def test_reading_preferences_returns_every_setting() -> None:
    preferences = await PreferencesService(_Repository(_user())).get("user")

    assert preferences.explanation_language.value == "zh"
    assert preferences.answer_language.value == "en"
    assert preferences.default_question_count == 5
    assert preferences.include_language_feedback is False


async def test_a_partial_update_leaves_untouched_settings_alone() -> None:
    repository = _Repository(_user())
    service = PreferencesService(repository)

    result = await service.update(
        "user", UserPreferencesUpdate(default_question_count=3, include_language_feedback=True)
    )

    assert result.default_question_count == 3
    assert result.include_language_feedback is True
    # Saving one field must not reset the rest of the learner's settings.
    assert result.explanation_language.value == "zh"
    assert result.explanation_style.value == "deep"
    assert result.default_question_type.value == "single_choice"


async def test_enum_values_are_stored_as_plain_strings() -> None:
    repository = _Repository(_user())

    await PreferencesService(repository).update(
        "user", UserPreferencesUpdate(explanation_style="socratic", default_difficulty="advanced")
    )

    # The ORM column is a string; storing an Enum instance would break comparisons.
    assert repository.saved.explanation_style == "socratic"
    assert repository.saved.default_difficulty == "advanced"


async def test_updating_a_missing_user_is_not_found() -> None:
    with pytest.raises(ResourceNotFoundError):
        await PreferencesService(_Repository(None)).update("user", UserPreferencesUpdate())


@pytest.mark.parametrize("count", [0, 11, -1])
def test_question_count_stays_within_the_supported_range(count) -> None:
    with pytest.raises(ValidationError):
        UserPreferencesUpdate(default_question_count=count)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("explanation_language", "fr"),
        ("explanation_style", "verbose"),
        ("default_question_type", "essay"),
        ("default_difficulty", "impossible"),
    ],
)
def test_unknown_preference_values_are_rejected(field, value) -> None:
    with pytest.raises(ValidationError):
        UserPreferencesUpdate(**{field: value})


def test_read_model_never_exposes_account_fields() -> None:
    payload = _to_read(_user()).model_dump()

    assert "email" not in payload
    assert "id" not in payload
