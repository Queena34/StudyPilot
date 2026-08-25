"""Create question attempts.

Revision ID: 0005
Revises: 0004
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("criterion_results_json", postgresql.JSONB(), nullable=False),
        sa.Column("feedback_json", postgresql.JSONB(), nullable=False),
        sa.Column("question_snapshot_json", postgresql.JSONB(), nullable=False),
        sa.Column("rubric_snapshot_json", postgresql.JSONB(), nullable=False),
        sa.Column("source_refs_json", postgresql.JSONB(), nullable=False),
        sa.Column("evaluation_model", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="ck_attempts_score"),
    )
    op.create_index("ix_attempts_user_id", "attempts", ["user_id"])
    op.create_index("ix_attempts_question_id", "attempts", ["question_id"])
    op.create_index(
        "ix_attempts_question_created", "attempts", ["question_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_table("attempts")
