"""Re-index every document in place.

Needed whenever the embedding model, the chunker or the collection version
changes: existing vectors were produced by the old configuration and cannot be
compared against new ones. Queues the same ingestion job the upload path uses,
so re-indexing and first indexing follow exactly one code path.

    python -m app.tasks.reindex
"""

import asyncio
import logging

from sqlalchemy import select

from app.domain.models import Document, DocumentStatus, Job, JobStatus
from app.infrastructure.database import SessionFactory, dispose_database

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


async def queue_reindex() -> int:
    async with SessionFactory() as session:
        result = await session.execute(
            select(Document).where(Document.deleted_at.is_(None))
        )
        documents = list(result.scalars())
        for document in documents:
            document.status = DocumentStatus.QUEUED.value
            document.error_message = None
            session.add(
                Job(
                    user_id=document.user_id,
                    document_id=document.id,
                    job_type="document_ingestion",
                    status=JobStatus.QUEUED.value,
                )
            )
        await session.commit()
        return len(documents)


async def main() -> None:
    count = await queue_reindex()
    logger.info("已排入重新入库任务：%d 份资料。Worker 会依次处理。", count)
    await dispose_database()


if __name__ == "__main__":
    asyncio.run(main())
