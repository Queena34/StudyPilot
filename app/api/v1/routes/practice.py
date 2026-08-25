from uuid import UUID

from fastapi import APIRouter, status

from app.api.dependencies import CurrentUserId, DbSession
from app.infrastructure.repositories.course_repository import CourseRepository
from app.infrastructure.repositories.practice_repository import PracticeRepository
from app.schemas.practice import PracticeSetCreate, PracticeSetRead
from app.services.practice_service import PracticeService

router = APIRouter()


def _service(session: DbSession) -> PracticeService:
    return PracticeService(CourseRepository(session), PracticeRepository(session))


@router.post(
    "/courses/{course_id}/practice-sets",
    response_model=PracticeSetRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_practice_set(
    course_id: UUID,
    body: PracticeSetCreate,
    session: DbSession,
    user_id: CurrentUserId,
) -> PracticeSetRead:
    return await _service(session).create(user_id, course_id, body)


@router.get("/practice-sets/{practice_set_id}", response_model=PracticeSetRead)
async def get_practice_set(
    practice_set_id: UUID,
    session: DbSession,
    user_id: CurrentUserId,
) -> PracticeSetRead:
    return await _service(session).get(user_id, practice_set_id)
