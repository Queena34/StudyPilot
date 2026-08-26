from uuid import UUID

from fastapi import APIRouter, Response, status

from app.api.dependencies import CurrentUserId, DbSession
from app.core.exceptions import ResourceNotFoundError
from app.infrastructure.repositories.course_repository import CourseRepository
from app.infrastructure.repositories.progress_repository import ProgressRepository
from app.schemas.progress import (
    CourseProgressRead,
    RecommendationList,
    TopicMasteryRead,
)
from app.services.progress_service import ProgressService

router = APIRouter()


def _service(session: DbSession) -> ProgressService:
    return ProgressService(CourseRepository(session), ProgressRepository(session))


@router.get("/{course_id}/progress", response_model=CourseProgressRead)
async def get_course_progress(
    course_id: UUID, session: DbSession, user_id: CurrentUserId
) -> CourseProgressRead:
    return await _service(session).overview(user_id, course_id)


@router.get("/{course_id}/topics", response_model=list[TopicMasteryRead])
async def list_course_topics(
    course_id: UUID, session: DbSession, user_id: CurrentUserId
) -> list[TopicMasteryRead]:
    return await _service(session).topics(user_id, course_id)


@router.get("/{course_id}/recommendations", response_model=RecommendationList)
async def get_course_recommendations(
    course_id: UUID, session: DbSession, user_id: CurrentUserId
) -> RecommendationList:
    return await _service(session).recommendations(user_id, course_id)


@router.delete("/{course_id}/topics/{topic}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_topic(
    course_id: UUID, topic: str, session: DbSession, user_id: CurrentUserId
) -> Response:
    removed = await ProgressRepository(session).delete_topic(user_id, course_id, topic)
    if not removed:
        raise ResourceNotFoundError("知识点")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{course_id}/progress", status_code=status.HTTP_204_NO_CONTENT)
async def clear_course_progress(
    course_id: UUID, session: DbSession, user_id: CurrentUserId
) -> Response:
    await _service(session).clear(user_id, course_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
