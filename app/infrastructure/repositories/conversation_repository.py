from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Conversation, Message


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(
        self, user_id: UUID, course_id: UUID, conversation_id: UUID
    ) -> Conversation | None:
        result = await self.session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
                Conversation.course_id == course_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_course(
        self, user_id: UUID, course_id: UUID, *, offset: int, limit: int
    ) -> list[Conversation]:
        result = await self.session.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id, Conversation.course_id == course_id)
            .order_by(Conversation.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars())

    async def recent_messages(
        self, user_id: UUID, conversation_id: UUID, *, limit: int = 8
    ) -> list[Message]:
        result = await self.session.execute(
            select(Message)
            .where(Message.user_id == user_id, Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def list_messages(
        self, user_id: UUID, conversation_id: UUID, *, offset: int, limit: int
    ) -> list[Message]:
        result = await self.session.execute(
            select(Message)
            .where(Message.user_id == user_id, Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars())

    async def save_exchange(
        self,
        *,
        conversation: Conversation,
        user_message: Message,
        assistant_message: Message,
    ) -> None:
        conversation.updated_at = datetime.now(timezone.utc)
        self.session.add_all([conversation, user_message, assistant_message])
        await self.session.commit()
