from uuid import UUID

from fastapi import APIRouter, Query, Response

from app.api.dependencies import CurrentUserId, DbSession
from app.core.exceptions import ResourceNotFoundError
from app.infrastructure.repositories.conversation_repository import ConversationRepository
from app.infrastructure.repositories.course_repository import CourseRepository
from app.infrastructure.repositories.document_repository import DocumentRepository
from app.infrastructure.repositories.progress_repository import ProgressRepository
from app.infrastructure.repositories.practice_repository import PracticeRepository
from app.infrastructure.repositories.study_plan_repository import StudyPlanRepository
from app.schemas.tutor import (
    Citation,
    ConversationList,
    ConversationRead,
    MessageList,
    StoredMessageRead,
    TutorMessageCreate,
    TutorMessageRead,
)
from app.services.attempt_service import AttemptService
from app.services.practice_service import PracticeService
from app.services.study_plan_service import StudyPlanService
from app.services.tutor_service import TutorService

router = APIRouter()


@router.post("/{course_id}/tutor/messages", response_model=TutorMessageRead)
async def create_tutor_message(
    course_id: UUID,
    body: TutorMessageCreate,
    session: DbSession,
    user_id: CurrentUserId,
    response: Response,
) -> TutorMessageRead:
    course_repository = CourseRepository(session)
    practice_repository = PracticeRepository(session)
    progress_repository = ProgressRepository(session)
    study_plan_repository = StudyPlanRepository(session)
    result = await TutorService(
        course_repository,
        ConversationRepository(session),
        DocumentRepository(session),
        progress_repository,
        study_plan_repository,
        PracticeService(course_repository, practice_repository),
        attempt_service=AttemptService(practice_repository, progress_repository),
        study_plan_service=StudyPlanService(
            course_repository, progress_repository, study_plan_repository
        ),
        practice_repository=practice_repository,
    ).answer(user_id, course_id, body)
    response.headers["x-trace-id"] = str(result.trace["trace_id"])
    return result


@router.get("/{course_id}/tutor/conversations", response_model=ConversationList)
async def list_tutor_conversations(
    course_id: UUID,
    session: DbSession,
    user_id: CurrentUserId,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
) -> ConversationList:
    if await CourseRepository(session).get(user_id, course_id) is None:
        raise ResourceNotFoundError("课程")
    items = await ConversationRepository(session).list_for_course(
        user_id, course_id, offset=(page - 1) * size, limit=size
    )
    return ConversationList(
        items=[ConversationRead.model_validate(item, from_attributes=True) for item in items],
        page=page,
        size=size,
    )


@router.get(
    "/{course_id}/tutor/conversations/{conversation_id}/messages",
    response_model=MessageList,
)
async def list_tutor_messages(
    course_id: UUID,
    conversation_id: UUID,
    session: DbSession,
    user_id: CurrentUserId,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
) -> MessageList:
    if await CourseRepository(session).get(user_id, course_id) is None:
        raise ResourceNotFoundError("课程")
    repository = ConversationRepository(session)
    if await repository.get(user_id, course_id, conversation_id) is None:
        raise ResourceNotFoundError("对话")
    messages = await repository.list_messages(
        user_id, conversation_id, offset=(page - 1) * size, limit=size
    )
    return MessageList(
        items=[
            StoredMessageRead(
                id=item.id,
                conversation_id=item.conversation_id,
                role=item.role,
                content=item.content,
                citations=[Citation.model_validate(value) for value in item.citations_json],
                model_name=item.model_name,
                latency_ms=item.latency_ms,
                created_at=item.created_at,
            )
            for item in messages
        ],
        page=page,
        size=size,
    )
