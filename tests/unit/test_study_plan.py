from datetime import date

from app.services.study_plan_service import (
    _daily_allocations,
    _schedule_dates,
    _task_description,
)


def test_schedule_can_exclude_weekends() -> None:
    dates = _schedule_dates(date(2026, 8, 24), date(2026, 8, 30), False)

    assert len(dates) == 5
    assert all(item.weekday() < 5 for item in dates)


def test_daily_allocations_respect_time_budget() -> None:
    regular = _daily_allocations(60, is_final_day=False)
    final = _daily_allocations(60, is_final_day=True)

    assert sum(minutes for _, minutes in regular) == 60
    assert regular == [("review", 36), ("practice", 24)]
    assert final == [("review", 36), ("checkpoint", 24)]


def test_short_sessions_stay_single_task() -> None:
    assert _daily_allocations(20, is_final_day=True) == [("review", 20)]


def test_weak_topic_description_is_actionable() -> None:
    description = _task_description("review", "Regularization", 0.2)

    assert "Regularization" in description
    assert "薄弱" in description
