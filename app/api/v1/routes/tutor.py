from uuid import UUID

from fastapi import APIRouter

from app.api.dependencies import CurrentUserId, DbSession
from app.infrastructure.repositories.course_repository import CourseRepository
from app.schemas.tutor import TutorMessageCreate, TutorMessageRead
from app.services.tutor_service import TutorService

router = APIRouter()


@router.post("/{course_id}/tutor/messages", response_model=TutorMessageRead)
async def create_tutor_message(
    course_id: UUID,
    body: TutorMessageCreate,
    session: DbSession,
    user_id: CurrentUserId,
) -> TutorMessageRead:
    return await TutorService(CourseRepository(session)).answer(user_id, course_id, body)
