from fastapi import APIRouter

from app.api.dependencies import CurrentUserId, DbSession
from app.infrastructure.repositories.user_repository import UserRepository
from app.schemas.preferences import UserPreferencesRead, UserPreferencesUpdate
from app.services.preferences_service import PreferencesService

router = APIRouter()


@router.get("/preferences", response_model=UserPreferencesRead)
async def read_preferences(
    session: DbSession, user_id: CurrentUserId
) -> UserPreferencesRead:
    return await PreferencesService(UserRepository(session)).get(user_id)


@router.patch("/preferences", response_model=UserPreferencesRead)
async def update_preferences(
    body: UserPreferencesUpdate, session: DbSession, user_id: CurrentUserId
) -> UserPreferencesRead:
    return await PreferencesService(UserRepository(session)).update(user_id, body)
