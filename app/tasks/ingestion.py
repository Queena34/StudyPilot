from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import and_, or_, select

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.domain.models import Document, DocumentStatus, Job, JobStatus
from app.infrastructure.database import SessionFactory
from app.infrastructure.file_storage import LocalFileStorage
from app.infrastructure.vector_store import CourseVectorStore
from app.rag.chunking import TextChunker
from app.rag.language import dominant_language
from app.rag.sections import detect_sections
from app.rag.parsers import parser_for_suffix


#: What to do with a job still marked running.
JOB_HEALTHY = "healthy"
JOB_REQUEUE = "requeue"
JOB_FAIL = "fail"


def stalled_job_action(
    *,
    started_at: datetime | None,
    now: datetime,
    lease_seconds: float,
    attempts: int,
    max_attempts: int,
) -> str:
    """Decide the fate of a job whose worker may have died holding it.

    Only queued jobs are ever claimed, so a worker that restarts mid-job leaves
    that job marked running with nobody to finish it — and the document stays
    "processing" forever, with no error and no retry offered to the learner.

    A job with no start time is already broken bookkeeping: requeue it rather
    than leave it stranded.
    """

    if started_at is None:
        return JOB_REQUEUE
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    if (now - started_at).total_seconds() < lease_seconds:
        return JOB_HEALTHY
    return JOB_FAIL if attempts >= max_attempts else JOB_REQUEUE


class DocumentIngestionService:
    def __init__(self) -> None:
        settings = get_settings()
        self.storage = LocalFileStorage(settings.upload_dir)
        self.chunker = TextChunker()

    async def reclaim_stalled_jobs(self) -> int:
        """Return jobs held by a dead worker, so the learner is not left waiting."""

        settings = get_settings()
        now = datetime.now(timezone.utc)
        reclaimed = 0
        async with SessionFactory() as session:
            result = await session.execute(
                select(Job).where(Job.status == JobStatus.RUNNING.value)
            )
            for job in result.scalars():
                action = stalled_job_action(
                    started_at=job.started_at,
                    now=now,
                    lease_seconds=settings.job_lease_seconds,
                    attempts=job.attempts,
                    max_attempts=settings.job_max_attempts,
                )
                if action == JOB_HEALTHY:
                    continue
                document = await session.get(Document, job.document_id)
                if action == JOB_FAIL:
                    job.status = JobStatus.FAILED.value
                    job.error_code = "JOB_STALLED"
                    job.error_message = "处理任务多次中断，请重新处理该资料。"
                    job.finished_at = now
                    if document is not None and job.job_type == "document_ingestion":
                        document.status = DocumentStatus.FAILED.value
                        document.error_code = "JOB_STALLED"
                        document.error_message = job.error_message
                else:
                    job.status = JobStatus.QUEUED.value
                    job.started_at = None
                    job.progress = 0
                    # The document has to move back too: a queued job whose
                    # document still says "processing" is never picked up,
                    # because claiming checks both rows.
                    if document is not None and job.job_type == "document_ingestion":
                        document.status = DocumentStatus.QUEUED.value
                reclaimed += 1
            if reclaimed:
                await session.commit()
        return reclaimed

    async def claim_next_job(self) -> UUID | None:
        await self.reclaim_stalled_jobs()
        async with SessionFactory() as session:
            result = await session.execute(
                select(Job)
                .join(Document, Document.id == Job.document_id)
                .where(
                    Job.status == JobStatus.QUEUED.value,
                    or_(
                        and_(
                            Job.job_type == "document_ingestion",
                            Document.status == DocumentStatus.QUEUED.value,
                            Document.deleted_at.is_(None),
                        ),
                        and_(
                            Job.job_type == "vector_cleanup",
                            Document.status == DocumentStatus.DELETED.value,
                            Document.deleted_at.is_not(None),
                        ),
                    ),
                )
                .order_by(Job.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            job = result.scalar_one_or_none()
            if job is None:
                return None
            now = datetime.now(timezone.utc)
            job.status = JobStatus.RUNNING.value
            job.started_at = now
            job.attempts += 1
            job.progress = 5
            document = await session.get(Document, job.document_id)
            if document is None:
                job.status = JobStatus.FAILED.value
                job.error_code = "DOCUMENT_NOT_FOUND"
                job.finished_at = now
                await session.commit()
                return None
            if job.job_type == "document_ingestion":
                document.status = DocumentStatus.PROCESSING.value
            await session.commit()
            return job.id

    async def process(self, job_id: UUID) -> None:
        document_id: UUID | None = None
        vector_store: CourseVectorStore | None = None
        try:
            async with SessionFactory() as session:
                job = await session.get(Job, job_id)
                if job is None:
                    return
                document = await session.get(Document, job.document_id)
                if document is None:
                    raise AppError("DOCUMENT_NOT_FOUND", "待处理文档不存在")
                document_id = document.id

                if job.job_type == "vector_cleanup":
                    vector_store = CourseVectorStore()
                    vector_store.delete_document(document.id)
                    job.status = JobStatus.SUCCEEDED.value
                    job.progress = 100
                    job.finished_at = datetime.now(timezone.utc)
                    await session.commit()
                    return

                if document.deleted_at is not None:
                    raise AppError("DOCUMENT_DELETED", "文档已删除")
                path = self.storage.resolve(document.storage_key)
                parsed = parser_for_suffix(Path(document.filename).suffix).parse(path)
                chunks = self.chunker.split(parsed)
                if not chunks:
                    raise AppError("EMPTY_DOCUMENT", "文档中没有可索引的文本")
                document.language = dominant_language([page.text for page in parsed.pages])
                sections = detect_sections(parsed)
                document.sections_json = [item.as_dict() for item in sections]
                job.progress = 45
                await session.commit()

                vector_store = CourseVectorStore()
                vector_store.delete_document(document.id)
                vector_store.add_document(
                    user_id=document.user_id,
                    course_id=document.course_id,
                    document_id=document.id,
                    filename=document.filename,
                    document_type=document.document_type,
                    language=document.language,
                    sections=sections,
                    chunks=chunks,
                )

                await session.refresh(document)
                if document.deleted_at is not None:
                    vector_store.delete_document(document.id)
                    job.status = JobStatus.CANCELLED.value
                    job.progress = 100
                    job.finished_at = datetime.now(timezone.utc)
                    await session.commit()
                    return

                now = datetime.now(timezone.utc)
                document.status = DocumentStatus.READY.value
                document.page_count = len(parsed.pages)
                document.chunk_count = len(chunks)
                document.processed_at = now
                document.error_code = None
                document.error_message = None
                job.status = JobStatus.SUCCEEDED.value
                job.progress = 100
                job.finished_at = now
                job.error_code = None
                job.error_message = None
                await session.commit()
        except Exception as exc:
            if document_id is not None and vector_store is not None:
                try:
                    vector_store.delete_document(document_id)
                except Exception:
                    pass
            await self._mark_failed(job_id, exc)

    async def _mark_failed(self, job_id: UUID, exc: Exception) -> None:
        code = exc.code if isinstance(exc, AppError) else "INGESTION_FAILED"
        message = exc.message if isinstance(exc, AppError) else "文档处理失败"
        async with SessionFactory() as session:
            job = await session.get(Job, job_id)
            if job is None:
                return
            document = await session.get(Document, job.document_id)
            now = datetime.now(timezone.utc)
            job.status = JobStatus.FAILED.value
            job.error_code = code
            job.error_message = message[:1000]
            job.finished_at = now
            if document is not None and job.job_type == "document_ingestion":
                document.status = DocumentStatus.FAILED.value
                document.error_code = code
                document.error_message = message[:1000]
            await session.commit()
