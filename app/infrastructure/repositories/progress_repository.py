import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Attempt, Question, TopicMastery


class ProgressRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record_attempt(
        self,
        attempt: Attempt,
        *,
        course_id: UUID,
        topics: list[str],
        errors: list[str],
    ) -> Attempt:
        self.session.add(attempt)
        now = datetime.now(timezone.utc)
        unique_topics = {_normalize_topic(topic): topic.strip() for topic in topics if topic.strip()}
        for normalized, display in sorted(unique_topics.items()):
            result = await self.session.execute(
                select(TopicMastery)
                .where(
                    TopicMastery.user_id == attempt.user_id,
                    TopicMastery.course_id == course_id,
                    TopicMastery.normalized_topic == normalized,
                )
                .with_for_update()
            )
            mastery = result.scalar_one_or_none()
            if mastery is None:
                mastery = TopicMastery(
                    user_id=attempt.user_id,
                    course_id=course_id,
                    normalized_topic=normalized,
                    display_topic=display,
                    status="unpracticed",
                    mastery_score=0,
                    average_score=0,
                    recent_score=0,
                    attempt_count=0,
                    common_errors_json={},
                )
                self.session.add(mastery)
            old_count = mastery.attempt_count
            new_count = old_count + 1
            mastery.average_score = round(
                (mastery.average_score * old_count + attempt.score) / new_count, 2
            )
            mastery.recent_score = round(
                attempt.score if old_count == 0 else 0.7 * attempt.score + 0.3 * mastery.recent_score,
                2,
            )
            mastery.attempt_count = new_count
            mastery.mastery_score = _mastery_score(
                mastery.recent_score, mastery.average_score, new_count
            )
            mastery.status = _mastery_status(mastery.mastery_score, new_count)
            mastery.common_errors_json = _merge_errors(mastery.common_errors_json, errors)
            mastery.last_practiced_at = now
            mastery.updated_at = now
        await self.session.commit()
        await self.session.refresh(attempt)
        return attempt

    async def list_topics(self, user_id: UUID, course_id: UUID) -> list[TopicMastery]:
        result = await self.session.execute(
            select(TopicMastery)
            .where(TopicMastery.user_id == user_id, TopicMastery.course_id == course_id)
            .order_by(TopicMastery.mastery_score, TopicMastery.display_topic)
        )
        return list(result.scalars())

    async def count_attempts(self, user_id: UUID, course_id: UUID) -> int:
        count = await self.session.scalar(
            select(func.count())
            .select_from(Attempt)
            .join(Question, Question.id == Attempt.question_id)
            .where(Attempt.user_id == user_id, Question.course_id == course_id)
        )
        return int(count or 0)

    async def clear(self, user_id: UUID, course_id: UUID) -> None:
        question_ids = select(Question.id).where(Question.course_id == course_id)
        await self.session.execute(
            delete(Attempt).where(
                Attempt.user_id == user_id,
                Attempt.question_id.in_(question_ids),
            )
        )
        await self.session.execute(
            delete(TopicMastery).where(
                TopicMastery.user_id == user_id, TopicMastery.course_id == course_id
            )
        )
        await self.session.commit()


def _normalize_topic(topic: str) -> str:
    return re.sub(r"\s+", " ", topic.strip().casefold())[:200]


def _mastery_score(recent_score: float, average_score: float, attempt_count: int) -> float:
    coverage = min(attempt_count / 3, 1.0)
    value = 0.6 * (recent_score / 100) + 0.3 * (average_score / 100) + 0.1 * coverage
    return round(min(1.0, max(0.0, value)), 4)


def _mastery_status(mastery_score: float, attempt_count: int) -> str:
    if attempt_count == 0:
        return "unpracticed"
    if mastery_score < 0.5:
        return "weak"
    if mastery_score < 0.8 or attempt_count < 2:
        return "learning"
    return "mastered"


def _merge_errors(current: dict, errors: list[str]) -> dict[str, int]:
    merged = {str(key): int(value) for key, value in (current or {}).items()}
    for error in errors:
        key = error.strip()[:300]
        if key:
            merged[key] = merged.get(key, 0) + 1
    return dict(sorted(merged.items(), key=lambda item: item[1], reverse=True)[:10])
