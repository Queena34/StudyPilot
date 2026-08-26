from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.domain.models import Document, DocumentStatus, Job, JobStatus


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_active_by_checksum(
        self, user_id: UUID, course_id: UUID, checksum: str
    ) -> Document | None:
        result = await self.session.execute(
            select(Document).where(
                Document.user_id == user_id,
                Document.course_id == course_id,
                Document.checksum_sha256 == checksum,
                Document.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def create_with_job(self, document: Document, job: Job) -> tuple[Document, Job]:
        self.session.add_all([document, job])
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("DUPLICATE_DOCUMENT", "该课程中已存在相同文件") from exc
        await self.session.refresh(document)
        await self.session.refresh(job)
        return document, job

    async def get(self, user_id: UUID, document_id: UUID) -> Document | None:
        result = await self.session.execute(
            select(Document).where(
                Document.id == document_id,
                Document.user_id == user_id,
                Document.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_for_course(
        self, user_id: UUID, course_id: UUID, *, offset: int, limit: int
    ) -> list[Document]:
        result = await self.session.execute(
            select(Document)
            .where(
                Document.user_id == user_id,
                Document.course_id == course_id,
                Document.deleted_at.is_(None),
            )
            .order_by(Document.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars())

    async def latest_job(self, user_id: UUID, document_id: UUID) -> Job | None:
        result = await self.session.execute(
            select(Job)
            .where(Job.user_id == user_id, Job.document_id == document_id)
            .order_by(Job.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def requeue(self, document: Document, job: Job) -> Job:
        """Queue a fresh ingestion attempt for a document that failed to process."""

        document.status = DocumentStatus.QUEUED.value
        document.error_message = None
        self.session.add_all([document, job])
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def mark_deleted(self, document: Document) -> None:
        now = datetime.now(timezone.utc)
        document.status = DocumentStatus.DELETED.value
        document.deleted_at = now
        await self.session.execute(
            update(Job)
            .where(
                Job.document_id == document.id,
                Job.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value]),
            )
            .values(status=JobStatus.CANCELLED.value, finished_at=now)
        )
        self.session.add(
            Job(
                user_id=document.user_id,
                document_id=document.id,
                job_type="vector_cleanup",
                status=JobStatus.QUEUED.value,
            )
        )
        await self.session.commit()
