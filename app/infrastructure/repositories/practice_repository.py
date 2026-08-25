from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models import Attempt, PracticeSet, Question


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

    async def get_question(self, user_id: UUID, question_id: UUID) -> Question | None:
        result = await self.session.execute(
            select(Question)
            .join(PracticeSet, PracticeSet.id == Question.practice_set_id)
            .where(Question.id == question_id, PracticeSet.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def create_attempt(self, attempt: Attempt) -> Attempt:
        self.session.add(attempt)
        await self.session.commit()
        await self.session.refresh(attempt)
        return attempt

    async def list_attempts(
        self, user_id: UUID, question_id: UUID, *, offset: int, limit: int
    ) -> list[Attempt]:
        result = await self.session.execute(
            select(Attempt)
            .where(Attempt.user_id == user_id, Attempt.question_id == question_id)
            .order_by(Attempt.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars())
