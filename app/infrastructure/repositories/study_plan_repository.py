from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models import StudyPlan, StudyTask


class StudyPlanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, plan: StudyPlan) -> StudyPlan:
        self.session.add(plan)
        await self.session.commit()
        return plan

    async def get(self, user_id: UUID, plan_id: UUID) -> StudyPlan | None:
        result = await self.session.execute(
            select(StudyPlan)
            .options(selectinload(StudyPlan.tasks))
            .where(StudyPlan.id == plan_id, StudyPlan.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_for_course(
        self, user_id: UUID, course_id: UUID, *, offset: int, limit: int
    ) -> list[StudyPlan]:
        result = await self.session.execute(
            select(StudyPlan)
            .options(selectinload(StudyPlan.tasks))
            .where(StudyPlan.user_id == user_id, StudyPlan.course_id == course_id)
            .order_by(StudyPlan.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars())

    async def get_task(self, user_id: UUID, task_id: UUID) -> StudyTask | None:
        result = await self.session.execute(
            select(StudyTask)
            .join(StudyPlan, StudyPlan.id == StudyTask.plan_id)
            .where(StudyTask.id == task_id, StudyPlan.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def save_task(self, task: StudyTask, user_id: UUID) -> StudyPlan:
        await self.session.commit()
        plan = await self.get(user_id, task.plan_id)
        if plan is None:
            raise RuntimeError("study plan disappeared while updating a task")
        if plan.tasks and all(item.status == "completed" for item in plan.tasks):
            plan.status = "completed"
            await self.session.commit()
        elif plan.status == "completed":
            plan.status = "active"
            await self.session.commit()
        return plan
