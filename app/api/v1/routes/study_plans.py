from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.dependencies import CurrentUserId, DbSession
from app.infrastructure.repositories.course_repository import CourseRepository
from app.infrastructure.repositories.progress_repository import ProgressRepository
from app.infrastructure.repositories.study_plan_repository import StudyPlanRepository
from app.schemas.study_plan import (
    StudyPlanCreate,
    StudyPlanList,
    StudyPlanRead,
    StudyTaskUpdate,
)
from app.services.study_plan_service import StudyPlanService

router = APIRouter()


def _service(session: DbSession) -> StudyPlanService:
    return StudyPlanService(
        CourseRepository(session),
        ProgressRepository(session),
        StudyPlanRepository(session),
    )


@router.post(
    "/courses/{course_id}/study-plans",
    response_model=StudyPlanRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_study_plan(
    course_id: UUID,
    body: StudyPlanCreate,
    session: DbSession,
    user_id: CurrentUserId,
) -> StudyPlanRead:
    return await _service(session).create(user_id, course_id, body)


@router.get("/courses/{course_id}/study-plans", response_model=StudyPlanList)
async def list_study_plans(
    course_id: UUID,
    session: DbSession,
    user_id: CurrentUserId,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
) -> StudyPlanList:
    items = await _service(session).list(user_id, course_id, page=page, size=size)
    return StudyPlanList(items=items, page=page, size=size)


@router.get("/study-plans/{plan_id}", response_model=StudyPlanRead)
async def get_study_plan(
    plan_id: UUID, session: DbSession, user_id: CurrentUserId
) -> StudyPlanRead:
    return await _service(session).get(user_id, plan_id)


@router.patch("/study-tasks/{task_id}", response_model=StudyPlanRead)
async def update_study_task(
    task_id: UUID,
    body: StudyTaskUpdate,
    session: DbSession,
    user_id: CurrentUserId,
) -> StudyPlanRead:
    return await _service(session).update_task(user_id, task_id, completed=body.completed)
