import argparse
import asyncio
import signal

from app.core.config import get_settings
from app.infrastructure.database import dispose_database
from app.tasks.ingestion import DocumentIngestionService


async def run_worker(*, once: bool = False) -> None:
    service = DocumentIngestionService()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop.set)

    try:
        while not stop.is_set():
            job_id = await service.claim_next_job()
            if job_id is not None:
                await service.process(job_id)
            if once:
                return
            if job_id is None:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=get_settings().worker_poll_seconds)
                except TimeoutError:
                    pass
    finally:
        await dispose_database()


def main() -> None:
    parser = argparse.ArgumentParser(description="StudyPilot document ingestion worker")
    parser.add_argument("--once", action="store_true", help="Process at most one queued job")
    args = parser.parse_args()
    asyncio.run(run_worker(once=args.once))


if __name__ == "__main__":
    main()
