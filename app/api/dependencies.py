from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.infrastructure.database import get_db_session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


async def get_current_user_id() -> UUID:
    # MVP runs as a single local user. Replace this dependency with JWT/OAuth later.
    return UUID(get_settings().development_user_id)


CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]

