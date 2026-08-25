"""Create topic mastery.

Revision ID: 0006
Revises: 0005
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "topic_mastery",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("normalized_topic", sa.String(200), primary_key=True),
        sa.Column("display_topic", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("mastery_score", sa.Float(), nullable=False),
        sa.Column("average_score", sa.Float(), nullable=False),
        sa.Column("recent_score", sa.Float(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("common_errors_json", postgresql.JSONB(), nullable=False),
        sa.Column("last_practiced_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("mastery_score >= 0 AND mastery_score <= 1", name="ck_topic_mastery_score"),
    )
    op.create_index("ix_topic_mastery_course_id", "topic_mastery", ["course_id"])
    op.create_index(
        "ix_topic_mastery_course_score", "topic_mastery", ["course_id", "mastery_score"]
    )


def downgrade() -> None:
    op.drop_table("topic_mastery")
