"""A worker that dies holding a job must not strand the learner's upload.

Only queued jobs are ever claimed, so a job left marked running has nobody to
finish it: the document sits at "processing" forever, showing no error and
offering no retry. These tests pin when a held job is taken back.
"""

from datetime import datetime, timedelta, timezone

from app.core.config import Settings
from app.tasks.ingestion import (
    JOB_FAIL,
    JOB_HEALTHY,
    JOB_REQUEUE,
    stalled_job_action,
)

LEASE = 1800.0
NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


def _action(minutes_ago: float, attempts: int = 1, max_attempts: int = 3) -> str:
    return stalled_job_action(
        started_at=NOW - timedelta(minutes=minutes_ago),
        now=NOW,
        lease_seconds=LEASE,
        attempts=attempts,
        max_attempts=max_attempts,
    )


def test_a_job_still_inside_its_lease_is_left_alone() -> None:
    """Embedding a 100-page PDF takes minutes; that worker is working, not dead."""

    assert _action(0.5) == JOB_HEALTHY
    assert _action(29) == JOB_HEALTHY


def test_a_job_past_its_lease_goes_back_to_the_queue() -> None:
    assert _action(31) == JOB_REQUEUE
    assert _action(60 * 24) == JOB_REQUEUE


def test_a_job_that_keeps_stalling_is_failed_rather_than_retried_forever() -> None:
    """Repeated stalls are a failing document, not bad luck.

    Failing it surfaces the problem to the learner, who can retry, instead of
    looping a worker that crashes on the same file every time.
    """

    assert _action(31, attempts=2) == JOB_REQUEUE
    assert _action(31, attempts=3) == JOB_FAIL
    assert _action(31, attempts=9) == JOB_FAIL


def test_a_job_with_no_start_time_is_requeued() -> None:
    """Bookkeeping is already broken; stranding it makes that permanent."""

    assert (
        stalled_job_action(
            started_at=None, now=NOW, lease_seconds=LEASE, attempts=0, max_attempts=3
        )
        == JOB_REQUEUE
    )


def test_a_naive_timestamp_is_read_as_utc() -> None:
    """A driver may hand back a naive datetime; comparing it must not explode."""

    assert (
        stalled_job_action(
            started_at=(NOW - timedelta(minutes=31)).replace(tzinfo=None),
            now=NOW,
            lease_seconds=LEASE,
            attempts=1,
            max_attempts=3,
        )
        == JOB_REQUEUE
    )


def test_the_lease_outlasts_a_real_ingestion() -> None:
    """A lease shorter than a real job would rob a healthy worker of its work."""

    settings = Settings()
    assert settings.job_lease_seconds >= 900
    assert settings.job_max_attempts >= 2
