from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from app.core.exceptions import AppError, ResourceNotFoundError
from app.domain.models import StudyPlan, StudyTask
from app.infrastructure.repositories.course_repository import CourseRepository
from app.infrastructure.repositories.progress_repository import ProgressRepository
from app.infrastructure.repositories.study_plan_repository import StudyPlanRepository
from app.schemas.study_plan import (
    StudyPlanCreate,
    StudyPlanRead,
    StudyTaskRead,
)


class StudyPlanService:
    def __init__(
        self,
        course_repository: CourseRepository,
        progress_repository: ProgressRepository,
        plan_repository: StudyPlanRepository,
    ) -> None:
        self.course_repository = course_repository
        self.progress_repository = progress_repository
        self.plan_repository = plan_repository

    async def create(
        self, user_id: UUID, course_id: UUID, data: StudyPlanCreate
    ) -> StudyPlanRead:
        course = await self.course_repository.get(user_id, course_id)
        if course is None:
            raise ResourceNotFoundError("课程")
        start = data.start_date or date.today()
        if course.exam_date and course.exam_date < start:
            raise AppError("EXAM_DATE_PASSED", "课程考试日期早于计划开始日期", status_code=422)
        requested_end = start + timedelta(days=data.duration_days - 1)
        end = min(requested_end, course.exam_date) if course.exam_date else requested_end
        study_dates = _schedule_dates(start, end, data.include_weekends)
        if not study_dates:
            raise AppError("NO_STUDY_DAYS", "计划范围内没有可安排的学习日", status_code=422)

        mastery = await self.progress_repository.list_topics(user_id, course_id)
        topics = [item.display_topic for item in mastery] or [course.name]
        topic_scores = {item.display_topic: item.mastery_score for item in mastery}
        plan = StudyPlan(
            user_id=user_id,
            course_id=course_id,
            title=data.title or f"{course.name} 学习计划",
            status="active",
            start_date=start,
            end_date=end,
            daily_minutes=data.daily_minutes,
            configuration_json=data.model_dump(mode="json"),
        )
        sequence = 1
        for day_index, scheduled_date in enumerate(study_dates):
            topic = topics[day_index % len(topics)]
            score = topic_scores.get(topic, 0)
            allocations = _daily_allocations(
                data.daily_minutes, is_final_day=scheduled_date == study_dates[-1]
            )
            for task_type, minutes in allocations:
                plan.tasks.append(
                    StudyTask(
                        scheduled_date=scheduled_date,
                        sequence=sequence,
                        task_type=task_type,
                        topic=topic,
                        title=_task_title(task_type, topic),
                        description=_task_description(task_type, topic, score),
                        estimated_minutes=minutes,
                        status="pending",
                    )
                )
                sequence += 1
        await self.plan_repository.create(plan)
        return _to_read(plan)

    async def get(self, user_id: UUID, plan_id: UUID) -> StudyPlanRead:
        plan = await self.plan_repository.get(user_id, plan_id)
        if plan is None:
            raise ResourceNotFoundError("学习计划")
        return _to_read(plan)

    async def list(
        self, user_id: UUID, course_id: UUID, *, page: int, size: int
    ) -> list[StudyPlanRead]:
        if await self.course_repository.get(user_id, course_id) is None:
            raise ResourceNotFoundError("课程")
        plans = await self.plan_repository.list_for_course(
            user_id, course_id, offset=(page - 1) * size, limit=size
        )
        return [_to_read(item) for item in plans]

    async def update_task(
        self, user_id: UUID, task_id: UUID, *, completed: bool
    ) -> StudyPlanRead:
        task = await self.plan_repository.get_task(user_id, task_id)
        if task is None:
            raise ResourceNotFoundError("学习任务")
        task.status = "completed" if completed else "pending"
        task.completed_at = datetime.now(timezone.utc) if completed else None
        plan = await self.plan_repository.save_task(task, user_id)
        return _to_read(plan)


def _task_title(task_type: str, topic: str) -> str:
    labels = {"review": "复习", "practice": "练习", "checkpoint": "阶段检查"}
    return f"{labels[task_type]}：{topic}"


def _schedule_dates(start: date, end: date, include_weekends: bool) -> list[date]:
    return [
        start + timedelta(days=offset)
        for offset in range((end - start).days + 1)
        if include_weekends or (start + timedelta(days=offset)).weekday() < 5
    ]


def _daily_allocations(daily_minutes: int, *, is_final_day: bool) -> list[tuple[str, int]]:
    if daily_minutes < 30:
        return [("review", daily_minutes)]
    review_minutes = round(daily_minutes * 0.6)
    second_type = "checkpoint" if is_final_day else "practice"
    return [("review", review_minutes), (second_type, daily_minutes - review_minutes)]


def _task_description(task_type: str, topic: str, mastery_score: float) -> str:
    if task_type == "review":
        level = "薄弱" if mastery_score < 0.5 else "待巩固"
        return f"回顾课程资料中的 {topic}，重点整理{level}概念和常见错误。"
    if task_type == "practice":
        return f"完成一组关于 {topic} 的练习，并根据反馈修正答案。"
    return f"用不查看资料的方式总结 {topic}，检查是否能够独立解释。"


def _to_read(plan: StudyPlan) -> StudyPlanRead:
    ordered = sorted(plan.tasks, key=lambda item: item.sequence)
    completed = sum(item.status == "completed" for item in ordered)
    return StudyPlanRead(
        id=plan.id,
        course_id=plan.course_id,
        title=plan.title,
        status=plan.status,
        start_date=plan.start_date,
        end_date=plan.end_date,
        daily_minutes=plan.daily_minutes,
        completion_rate=round(completed / max(1, len(ordered)), 4),
        created_at=plan.created_at,
        tasks=[
            StudyTaskRead(
                id=item.id,
                scheduled_date=item.scheduled_date,
                sequence=item.sequence,
                task_type=item.task_type,
                topic=item.topic,
                title=item.title,
                description=item.description,
                estimated_minutes=item.estimated_minutes,
                status=item.status,
                completed_at=item.completed_at,
            )
            for item in ordered
        ],
    )
