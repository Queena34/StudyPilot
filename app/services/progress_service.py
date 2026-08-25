from uuid import UUID

from app.core.exceptions import ResourceNotFoundError
from app.infrastructure.repositories.course_repository import CourseRepository
from app.infrastructure.repositories.progress_repository import ProgressRepository
from app.schemas.progress import (
    CourseProgressRead,
    RecommendationList,
    RecommendationRead,
    TopicMasteryRead,
)


class ProgressService:
    def __init__(
        self, course_repository: CourseRepository, progress_repository: ProgressRepository
    ) -> None:
        self.course_repository = course_repository
        self.progress_repository = progress_repository

    async def topics(self, user_id: UUID, course_id: UUID) -> list[TopicMasteryRead]:
        await self._ensure_course(user_id, course_id)
        items = await self.progress_repository.list_topics(user_id, course_id)
        return [
            TopicMasteryRead(
                topic=item.display_topic,
                status=item.status,
                mastery_score=item.mastery_score,
                average_score=item.average_score,
                recent_score=item.recent_score,
                attempt_count=item.attempt_count,
                common_errors=item.common_errors_json,
                last_practiced_at=item.last_practiced_at,
            )
            for item in items
        ]

    async def overview(self, user_id: UUID, course_id: UUID) -> CourseProgressRead:
        topics = await self.topics(user_id, course_id)
        total_attempts = await self.progress_repository.count_attempts(user_id, course_id)
        return CourseProgressRead(
            course_id=course_id,
            overall_mastery=round(
                sum(item.mastery_score for item in topics) / max(1, len(topics)), 4
            ),
            practiced_topics=len(topics),
            total_attempts=total_attempts,
            weak_topics=sum(item.status == "weak" for item in topics),
            learning_topics=sum(item.status == "learning" for item in topics),
            mastered_topics=sum(item.status == "mastered" for item in topics),
        )

    async def recommendations(self, user_id: UUID, course_id: UUID) -> RecommendationList:
        topics = await self.topics(user_id, course_id)
        candidates = [item for item in topics if item.status != "mastered"][:5]
        return RecommendationList(
            items=[
                RecommendationRead(
                    topic=item.topic,
                    mastery_score=item.mastery_score,
                    priority=index,
                    reason=(
                        "该知识点最近作答表现较弱。"
                        if item.status == "weak"
                        else "该知识点仍处于学习巩固阶段。"
                    ),
                    suggested_action="复习对应课程来源后，再完成一道针对性练习。",
                )
                for index, item in enumerate(candidates, start=1)
            ]
        )

    async def clear(self, user_id: UUID, course_id: UUID) -> None:
        await self._ensure_course(user_id, course_id)
        await self.progress_repository.clear(user_id, course_id)

    async def _ensure_course(self, user_id: UUID, course_id: UUID) -> None:
        if await self.course_repository.get(user_id, course_id) is None:
            raise ResourceNotFoundError("课程")
