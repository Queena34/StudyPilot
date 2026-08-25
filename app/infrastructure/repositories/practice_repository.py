from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models import PracticeSet


class PracticeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, practice_set: PracticeSet) -> PracticeSet:
        self.session.add(practice_set)
        await self.session.commit()
        return practice_set

    async def get(self, user_id: UUID, practice_set_id: UUID) -> PracticeSet | None:
        result = await self.session.execute(
            select(PracticeSet)
            .options(selectinload(PracticeSet.questions))
            .where(PracticeSet.id == practice_set_id, PracticeSet.user_id == user_id)
        )
        return result.scalar_one_or_none()
