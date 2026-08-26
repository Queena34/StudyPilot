from uuid import UUID

from app.core.exceptions import ResourceNotFoundError
from app.infrastructure.repositories.user_repository import UserRepository
from app.schemas.preferences import UserPreferencesRead, UserPreferencesUpdate


class PreferencesService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    async def get(self, user_id: UUID) -> UserPreferencesRead:
        return _to_read(await self._require(user_id))

    async def update(
        self, user_id: UUID, data: UserPreferencesUpdate
    ) -> UserPreferencesRead:
        user = await self._require(user_id)
        # Only fields the learner actually sent are changed, so a partial save
        # never silently resets the rest of their settings.
        for field, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
            setattr(user, field, value.value if hasattr(value, "value") else value)
        return _to_read(await self.repository.save(user))

    async def _require(self, user_id: UUID):
        user = await self.repository.get(user_id)
        if user is None:
            raise ResourceNotFoundError("用户")
        return user


def _to_read(user) -> UserPreferencesRead:
    return UserPreferencesRead(
        explanation_language=user.explanation_language,
        answer_language=user.answer_language,
        explanation_style=user.explanation_style,
        default_question_type=user.default_question_type,
        default_difficulty=user.default_difficulty,
        default_question_count=user.default_question_count,
        include_language_feedback=user.include_language_feedback,
    )
