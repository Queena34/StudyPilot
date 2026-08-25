from uuid import UUID

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from app.api.dependencies import CurrentUserId, DbSession
from app.infrastructure.repositories.course_repository import CourseRepository
from app.infrastructure.repositories.document_repository import DocumentRepository
from app.schemas.document import DocumentList, DocumentRead, DocumentType, JobSummary
from app.services.document_service import DocumentService

router = APIRouter()


def _service(session: DbSession) -> DocumentService:
    return DocumentService(DocumentRepository(session), CourseRepository(session))


def _response(document, job) -> DocumentRead:
    result = DocumentRead.model_validate(document)
    if job is not None:
        result.job = JobSummary(id=job.id, status=job.status, progress=job.progress)
    return result


@router.post(
    "/courses/{course_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    course_id: UUID,
    session: DbSession,
    user_id: CurrentUserId,
    file: UploadFile = File(...),
    document_type: DocumentType = Form(default=DocumentType.OTHER),
) -> DocumentRead:
    document, job = await _service(session).upload(user_id, course_id, file, document_type)
    return _response(document, job)


@router.get("/courses/{course_id}/documents", response_model=DocumentList)
async def list_documents(
    course_id: UUID,
    session: DbSession,
    user_id: CurrentUserId,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
) -> DocumentList:
    items = await _service(session).list(user_id, course_id, page=page, size=size)
    return DocumentList(
        items=[_response(document, job) for document, job in items],
        page=page,
        size=size,
    )


@router.get("/documents/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: UUID, session: DbSession, user_id: CurrentUserId
) -> DocumentRead:
    document, job = await _service(session).get(user_id, document_id)
    return _response(document, job)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID, session: DbSession, user_id: CurrentUserId
) -> Response:
    await _service(session).delete(user_id, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

