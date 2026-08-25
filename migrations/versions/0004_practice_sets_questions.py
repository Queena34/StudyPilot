"""Create practice sets and questions.

Revision ID: 0004
Revises: 0003
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "practice_sets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("configuration_json", postgresql.JSONB(), nullable=False),
        sa.Column("model_name", sa.String(120), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_practice_sets_user_id", "practice_sets", ["user_id"])
    op.create_index("ix_practice_sets_course_id", "practice_sets", ["course_id"])

    op.create_table(
        "questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("practice_set_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("practice_sets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_type", sa.String(32), nullable=False),
        sa.Column("difficulty", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("options_json", postgresql.JSONB()),
        sa.Column("knowledge_points_json", postgresql.JSONB(), nullable=False),
        sa.Column("reference_answer", sa.Text(), nullable=False),
        sa.Column("rubric_json", postgresql.JSONB(), nullable=False),
        sa.Column("source_refs_json", postgresql.JSONB(), nullable=False),
        sa.Column("generation_metadata_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_questions_practice_set_id", "questions", ["practice_set_id"])
    op.create_index("ix_questions_course_id", "questions", ["course_id"])


def downgrade() -> None:
    op.drop_table("questions")
    op.drop_table("practice_sets")
