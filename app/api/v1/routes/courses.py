from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.api.dependencies import CurrentUserId, DbSession
from app.infrastructure.repositories.course_repository import CourseRepository
from app.schemas.course import CourseCreate, CourseList, CourseRead, CourseUpdate
from app.services.course_service import CourseService

router = APIRouter()


def _service(session: DbSession) -> CourseService:
    return CourseService(CourseRepository(session))


@router.post("", response_model=CourseRead, status_code=status.HTTP_201_CREATED)
async def create_course(
    body: CourseCreate, session: DbSession, user_id: CurrentUserId
) -> CourseRead:
    course = await _service(session).create(user_id, body)
    return CourseRead.model_validate(course)


@router.get("", response_model=CourseList)
async def list_courses(
    session: DbSession,
    user_id: CurrentUserId,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
) -> CourseList:
    items, total = await _service(session).list(user_id, page=page, size=size)
    return CourseList(
        items=[CourseRead.model_validate(item) for item in items],
        page=page,
        size=size,
        total=total,
    )


@router.get("/{course_id}", response_model=CourseRead)
async def get_course(
    course_id: UUID, session: DbSession, user_id: CurrentUserId
) -> CourseRead:
    return CourseRead.model_validate(await _service(session).get(user_id, course_id))


@router.patch("/{course_id}", response_model=CourseRead)
async def update_course(
    course_id: UUID,
    body: CourseUpdate,
    session: DbSession,
    user_id: CurrentUserId,
) -> CourseRead:
    course = await _service(session).update(user_id, course_id, body)
    return CourseRead.model_validate(course)


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_course(
    course_id: UUID, session: DbSession, user_id: CurrentUserId
) -> Response:
    await _service(session).delete(user_id, course_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

