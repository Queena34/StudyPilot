from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.exceptions import AppError, ConflictError, ResourceNotFoundError
from app.domain.models import Document, DocumentStatus, Job, JobStatus
from app.infrastructure.file_storage import LocalFileStorage
from app.infrastructure.repositories.course_repository import CourseRepository
from app.infrastructure.repositories.document_repository import DocumentRepository
from app.schemas.document import DocumentType

ALLOWED_UPLOADS = {
    ".pdf": {"application/pdf", "application/octet-stream"},
    ".md": {"text/markdown", "text/plain", "application/octet-stream"},
    ".txt": {"text/plain", "application/octet-stream"},
}


class DocumentService:
    def __init__(
        self,
        repository: DocumentRepository,
        course_repository: CourseRepository,
        storage: LocalFileStorage | None = None,
    ) -> None:
        self.repository = repository
        self.course_repository = course_repository
        self.storage = storage or LocalFileStorage(get_settings().upload_dir)

    async def upload(
        self,
        user_id: UUID,
        course_id: UUID,
        upload: UploadFile,
        document_type: DocumentType,
    ) -> tuple[Document, Job]:
        if await self.course_repository.get(user_id, course_id) is None:
            raise ResourceNotFoundError("课程")

        filename = Path((upload.filename or "").replace("\\", "/")).name.strip()
        if not filename or filename in {".", ".."}:
            raise AppError("INVALID_FILENAME", "文件名不合法", status_code=400)
        suffix = Path(filename).suffix.lower()
        allowed_mimes = ALLOWED_UPLOADS.get(suffix)
        if allowed_mimes is None:
            raise AppError("UNSUPPORTED_FILE_TYPE", "仅支持PDF、Markdown和TXT文件", status_code=415)
        mime_type = (upload.content_type or "application/octet-stream").lower()
        if mime_type not in allowed_mimes:
            raise AppError(
                "MIME_TYPE_MISMATCH", "文件扩展名与内容类型不匹配", status_code=415
            )

        document_id = uuid4()
        stored = await self.storage.save_upload(
            upload,
            user_id=user_id,
            course_id=course_id,
            document_id=document_id,
            suffix=suffix,
            max_bytes=get_settings().max_upload_mb * 1024 * 1024,
        )
        try:
            duplicate = await self.repository.find_active_by_checksum(
                user_id, course_id, stored.checksum_sha256
            )
            if duplicate is not None:
                raise ConflictError("DUPLICATE_DOCUMENT", "该课程中已存在相同文件")
            document = Document(
                id=document_id,
                user_id=user_id,
                course_id=course_id,
                filename=filename,
                storage_key=stored.storage_key,
                checksum_sha256=stored.checksum_sha256,
                mime_type=mime_type,
                document_type=document_type.value,
                status=DocumentStatus.QUEUED.value,
                size_bytes=stored.size_bytes,
            )
            job = Job(
                user_id=user_id,
                document_id=document_id,
                job_type="document_ingestion",
                status=JobStatus.QUEUED.value,
            )
            return await self.repository.create_with_job(document, job)
        except Exception:
            self.storage.delete(stored.storage_key)
            raise

    async def get(self, user_id: UUID, document_id: UUID) -> tuple[Document, Job | None]:
        document = await self.repository.get(user_id, document_id)
        if document is None:
            raise ResourceNotFoundError("文档")
        return document, await self.repository.latest_job(user_id, document_id)

    async def list(
        self, user_id: UUID, course_id: UUID, *, page: int, size: int
    ) -> list[tuple[Document, Job | None]]:
        if await self.course_repository.get(user_id, course_id) is None:
            raise ResourceNotFoundError("课程")
        documents = await self.repository.list_for_course(
            user_id, course_id, offset=(page - 1) * size, limit=size
        )
        return [
            (document, await self.repository.latest_job(user_id, document.id))
            for document in documents
        ]

    async def reprocess(self, user_id: UUID, document_id: UUID) -> tuple[Document, Job]:
        """Retry a failed ingestion. Only a failed document may be requeued, so a
        successful one cannot be silently reprocessed into duplicate chunks."""

        document = await self.repository.get(user_id, document_id)
        if document is None:
            raise ResourceNotFoundError("资料")
        if document.status != DocumentStatus.FAILED.value:
            raise AppError(
                "DOCUMENT_NOT_RETRYABLE",
                "只有处理失败的资料才能重新处理",
                status_code=409,
            )
        job = Job(
            user_id=user_id,
            document_id=document.id,
            job_type="document_ingestion",
            status=JobStatus.QUEUED.value,
        )
        return document, await self.repository.requeue(document, job)

    async def delete(self, user_id: UUID, document_id: UUID) -> None:
        document, _ = await self.get(user_id, document_id)
        self.storage.delete(document.storage_key)
        await self.repository.mark_deleted(document)
