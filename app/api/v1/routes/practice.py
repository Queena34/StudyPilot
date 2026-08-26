from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.dependencies import CurrentUserId, DbSession
from app.infrastructure.repositories.course_repository import CourseRepository
from app.infrastructure.repositories.practice_repository import PracticeRepository
from app.infrastructure.repositories.progress_repository import ProgressRepository
from app.schemas.attempt import AttemptCreate, AttemptList, AttemptRead
from app.schemas.practice import PracticeSetCreate, PracticeSetList, PracticeSetRead
from app.services.attempt_service import AttemptService
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


@router.get("/courses/{course_id}/practice-sets", response_model=PracticeSetList)
async def list_course_practice_sets(
    course_id: UUID,
    session: DbSession,
    user_id: CurrentUserId,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=50),
) -> PracticeSetList:
    course_repository = CourseRepository(session)
    return await PracticeService(
        course_repository, PracticeRepository(session)
    ).list_for_course(user_id, course_id, page=page, size=size)


@router.get("/practice-sets/{practice_set_id}", response_model=PracticeSetRead)
async def get_practice_set(
    practice_set_id: UUID,
    session: DbSession,
    user_id: CurrentUserId,
) -> PracticeSetRead:
    return await _service(session).get(user_id, practice_set_id)


@router.post(
    "/questions/{question_id}/attempts",
    response_model=AttemptRead,
    status_code=status.HTTP_201_CREATED,
)
async def submit_attempt(
    question_id: UUID,
    body: AttemptCreate,
    session: DbSession,
    user_id: CurrentUserId,
) -> AttemptRead:
    return await AttemptService(
        PracticeRepository(session), ProgressRepository(session)
    ).submit(user_id, question_id, body)


@router.get("/questions/{question_id}/attempts", response_model=AttemptList)
async def list_attempts(
    question_id: UUID,
    session: DbSession,
    user_id: CurrentUserId,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
) -> AttemptList:
    items = await AttemptService(
        PracticeRepository(session), ProgressRepository(session)
    ).list(
        user_id, question_id, page=page, size=size
    )
    return AttemptList(items=items, page=page, size=size)
