from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Conversation, Course, PracticeSet, StudyPlan, TopicMastery


class CourseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, course: Course) -> Course:
        self.session.add(course)
        await self.session.commit()
        await self.session.refresh(course)
        return course

    async def get(self, user_id: UUID, course_id: UUID) -> Course | None:
        result = await self.session.execute(
            select(Course).where(
                Course.id == course_id,
                Course.user_id == user_id,
                Course.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self, user_id: UUID, *, offset: int, limit: int
    ) -> tuple[list[Course], int]:
        condition = (Course.user_id == user_id, Course.deleted_at.is_(None))
        rows = await self.session.execute(
            select(Course)
            .where(*condition)
            .order_by(Course.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        count = await self.session.scalar(select(func.count()).select_from(Course).where(*condition))
        return list(rows.scalars()), int(count or 0)

    async def save(self, course: Course) -> Course:
        await self.session.commit()
        await self.session.refresh(course)
        return course

    async def soft_delete(self, course: Course) -> None:
        await self.session.execute(
            delete(StudyPlan).where(StudyPlan.course_id == course.id)
        )
        await self.session.execute(
            delete(TopicMastery).where(TopicMastery.course_id == course.id)
        )
        await self.session.execute(
            delete(PracticeSet).where(PracticeSet.course_id == course.id)
        )
        await self.session.execute(
            delete(Conversation).where(Conversation.course_id == course.id)
        )
        course.deleted_at = datetime.now(timezone.utc)
        await self.session.commit()
