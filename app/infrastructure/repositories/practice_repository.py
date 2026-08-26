from uuid import UUID

from sqlalchemy import func, select
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

    async def list_for_course(
        self, user_id: UUID, course_id: UUID, *, offset: int, limit: int
    ) -> list[PracticeSet]:
        result = await self.session.execute(
            select(PracticeSet)
            .options(selectinload(PracticeSet.questions))
            .where(PracticeSet.user_id == user_id, PracticeSet.course_id == course_id)
            .order_by(PracticeSet.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().unique())

    async def best_scores_for_questions(
        self, user_id: UUID, question_ids: list[UUID]
    ) -> dict[UUID, float]:
        """Highest recorded score per question, used to mark what still needs work."""

        if not question_ids:
            return {}
        result = await self.session.execute(
            select(Attempt.question_id, func.max(Attempt.score))
            .where(Attempt.user_id == user_id, Attempt.question_id.in_(question_ids))
            .group_by(Attempt.question_id)
        )
        return {row[0]: float(row[1]) for row in result.all()}

    async def latest_pending_question(
        self, user_id: UUID, course_id: UUID
    ) -> Question | None:
        """The first still-unanswered question of the newest practice set.

        Used by the chat evaluator so a learner can answer in the conversation
        without having to name a question ID.
        """

        answered = select(Attempt.question_id).where(Attempt.user_id == user_id)
        result = await self.session.execute(
            select(Question)
            .join(PracticeSet, PracticeSet.id == Question.practice_set_id)
            .where(
                PracticeSet.user_id == user_id,
                PracticeSet.course_id == course_id,
                Question.id.not_in(answered),
            )
            .order_by(PracticeSet.created_at.desc(), Question.created_at.asc())
            .limit(1)
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
