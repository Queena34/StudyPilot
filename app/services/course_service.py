from uuid import UUID

from app.core.exceptions import ResourceNotFoundError
from app.domain.models import Course
from app.infrastructure.file_storage import LocalFileStorage
from app.infrastructure.repositories.course_repository import CourseRepository
from app.infrastructure.repositories.document_repository import DocumentRepository
from app.schemas.course import CourseCreate, CourseUpdate


class CourseService:
    def __init__(
        self,
        repository: CourseRepository,
        document_repository: DocumentRepository | None = None,
        storage: LocalFileStorage | None = None,
    ) -> None:
        self.repository = repository
        self.document_repository = document_repository
        self.storage = storage

    async def create(self, user_id: UUID, data: CourseCreate) -> Course:
        return await self.repository.create(Course(user_id=user_id, **data.model_dump()))

    async def get(self, user_id: UUID, course_id: UUID) -> Course:
        course = await self.repository.get(user_id, course_id)
        if course is None:
            raise ResourceNotFoundError("课程")
        return course

    async def list(
        self, user_id: UUID, *, page: int, size: int
    ) -> tuple[list[Course], int]:
        return await self.repository.list(user_id, offset=(page - 1) * size, limit=size)

    async def update(
        self, user_id: UUID, course_id: UUID, data: CourseUpdate
    ) -> Course:
        course = await self.get(user_id, course_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(course, field, value)
        return await self.repository.save(course)

    async def delete(self, user_id: UUID, course_id: UUID) -> None:
        course = await self.get(user_id, course_id)
        if self.document_repository is not None and self.storage is not None:
            documents = await self.document_repository.list_for_course(
                user_id, course_id, offset=0, limit=10_000
            )
            for document in documents:
                self.storage.delete(document.storage_key)
                await self.document_repository.mark_deleted(document)
        await self.repository.soft_delete(course)
