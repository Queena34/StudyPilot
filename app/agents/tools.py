"""Teaching tool layer (roadmap section 4.4).

Agents reach course data, practice, grading and planning only through this
manager. It enforces the access rules in one place — the course must belong to
the caller, and any requested document must belong to that course — and records
every call with its outcome, latency and failure reason, so a turn's tool usage
is auditable from the trace instead of from each agent's own bookkeeping.
"""

from uuid import UUID

from app.agents.protocol import ToolCall, timer
from app.core.exceptions import AppError, ResourceNotFoundError


class ToolPermissionError(AppError):
    """Raised when a tool call would step outside the caller's own course data."""

    def __init__(self, message: str) -> None:
        super().__init__("TOOL_SCOPE_DENIED", message, status_code=403)


class ToolSession:
    """One agent step's worth of tool calls, with its own recorded call list."""

    def __init__(self, manager: "TeachingToolManager") -> None:
        self.manager = manager
        self.calls: list[ToolCall] = []

    async def _invoke(self, name: str, action, *, detail=None):
        with timer() as elapsed:
            try:
                result = await action()
            except Exception as error:  # noqa: BLE001 - recorded, then re-raised
                self.calls.append(
                    ToolCall(
                        name,
                        ok=False,
                        latency_ms=elapsed.elapsed_ms,
                        detail=getattr(error, "code", type(error).__name__),
                    )
                )
                raise
        self.calls.append(
            ToolCall(
                name,
                ok=True,
                latency_ms=elapsed.elapsed_ms,
                detail=detail(result) if detail else None,
            )
        )
        return result

    async def search_course_material(
        self,
        context,
        *,
        query: str,
        top_k: int,
        document_types: list[str] | None,
        document_ids: list[UUID] | None,
        page_from: int | None,
        page_to: int | None,
    ):
        await self.manager.authorize(context)
        if document_ids:
            await self.manager.assert_documents_in_course(context, document_ids)

        async def action():
            return await self.manager.retriever.retrieve(
                user_id=context.user_id,
                course_id=context.course_id,
                query=query,
                top_k=top_k,
                document_types=document_types or None,
                document_ids=document_ids or None,
                page_from=page_from,
                page_to=page_to,
            )

        return await self._invoke(
            "search_course_material", action, detail=lambda items: f"{len(items)} chunk(s)"
        )

    async def list_course_documents(self, context, *, limit: int = 100):
        await self.manager.authorize(context)

        async def action():
            return await self.manager.document_repository.list_for_course(
                context.user_id, context.course_id, offset=0, limit=limit
            )

        return await self._invoke(
            "list_course_documents", action, detail=lambda items: f"{len(items)} document(s)"
        )

    async def get_learning_progress(self, context):
        await self.manager.authorize(context)

        async def action():
            topics = await self.manager.progress_repository.list_topics(
                context.user_id, context.course_id
            )
            attempts = await self.manager.progress_repository.count_attempts(
                context.user_id, context.course_id
            )
            return topics, attempts

        return await self._invoke(
            "get_learning_progress",
            action,
            detail=lambda pair: f"{len(pair[0])} topic(s), {pair[1]} attempt(s)",
        )

    async def get_recent_learning_context(self, context, *, limit: int = 6):
        """Recent conversation turns, for agents that need what came before."""

        async def action():
            return context.history[-limit:]

        return await self._invoke(
            "get_recent_learning_context", action, detail=lambda items: f"{len(items)} turn(s)"
        )

    async def list_study_plans(self, context, *, limit: int = 5):
        await self.manager.authorize(context)

        async def action():
            return await self.manager.study_plan_repository.list_for_course(
                context.user_id, context.course_id, offset=0, limit=limit
            )

        return await self._invoke(
            "list_study_plans", action, detail=lambda items: f"{len(items)} plan(s)"
        )

    async def create_study_plan(self, context, configuration):
        await self.manager.authorize(context)
        if self.manager.study_plan_service is None:
            raise ToolPermissionError("学习计划生成未启用")

        async def action():
            return await self.manager.study_plan_service.create(
                context.user_id, context.course_id, configuration
            )

        return await self._invoke(
            "create_study_plan", action, detail=lambda plan: f"{len(plan.tasks)} task(s)"
        )

    async def create_practice_set(self, context, configuration):
        await self.manager.authorize(context)
        scope = getattr(configuration, "scope", None)
        if scope is not None and scope.document_ids:
            await self.manager.assert_documents_in_course(context, scope.document_ids)

        async def action():
            return await self.manager.practice_service.create(
                context.user_id, context.course_id, configuration
            )

        return await self._invoke(
            "create_practice_set",
            action,
            detail=lambda item: f"{len(item.questions)} question(s)",
        )

    async def find_pending_question(self, context):
        await self.manager.authorize(context)

        async def action():
            return await self.manager.practice_repository.latest_pending_question(
                context.user_id, context.course_id
            )

        return await self._invoke(
            "find_pending_question",
            action,
            detail=lambda item: None if item else "no unanswered question",
        )

    async def grade_answer(self, context, question_id: UUID, data):
        """Grading also updates topic mastery inside AttemptService."""

        await self.manager.authorize(context)
        if self.manager.attempt_service is None:
            raise ToolPermissionError("批改服务未启用")

        async def action():
            return await self.manager.attempt_service.submit(
                context.user_id, question_id, data
            )

        return await self._invoke(
            "grade_answer", action, detail=lambda attempt: f"score {attempt.score}"
        )


class TeachingToolManager:
    """Builds tool sessions and owns the shared authorization checks."""

    def __init__(
        self,
        *,
        course_repository,
        document_repository,
        progress_repository,
        study_plan_repository,
        retriever,
        practice_service,
        practice_repository=None,
        attempt_service=None,
        study_plan_service=None,
    ) -> None:
        self.course_repository = course_repository
        self.document_repository = document_repository
        self.progress_repository = progress_repository
        self.study_plan_repository = study_plan_repository
        self.retriever = retriever
        self.practice_service = practice_service
        self.practice_repository = practice_repository
        self.attempt_service = attempt_service
        self.study_plan_service = study_plan_service
        self._authorized: set[tuple[UUID, UUID]] = set()
        self._course_documents: dict[tuple[UUID, UUID], set[UUID]] = {}

    def session(self) -> ToolSession:
        return ToolSession(self)

    async def authorize(self, context) -> None:
        """The course must exist and belong to the caller. Cached per manager."""

        key = (context.user_id, context.course_id)
        if key in self._authorized:
            return
        if await self.course_repository.get(context.user_id, context.course_id) is None:
            raise ResourceNotFoundError("课程")
        self._authorized.add(key)

    async def assert_documents_in_course(self, context, document_ids: list[UUID]) -> None:
        """A model-proposed or stale document ID must never reach another course."""

        key = (context.user_id, context.course_id)
        if key not in self._course_documents:
            documents = await self.document_repository.list_for_course(
                context.user_id, context.course_id, offset=0, limit=500
            )
            self._course_documents[key] = {item.id for item in documents}
        allowed = self._course_documents[key]
        outside = [str(item) for item in document_ids if item not in allowed]
        if outside:
            raise ToolPermissionError(
                f"指定的资料不属于当前课程：{', '.join(outside)}"
            )
