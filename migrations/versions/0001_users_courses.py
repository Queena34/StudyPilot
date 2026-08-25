"""Create users and courses.

Revision ID: 0001
Revises:
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEVELOPMENT_USER_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=True, unique=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("explanation_language", sa.String(16), nullable=False, server_default="zh"),
        sa.Column("answer_language", sa.String(16), nullable=False, server_default="en"),
        sa.Column("explanation_style", sa.String(32), nullable=False, server_default="deep"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "courses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("course_code", sa.String(80)),
        sa.Column("institution", sa.String(200)),
        sa.Column("semester", sa.String(80)),
        sa.Column("exam_date", sa.Date()),
        sa.Column("target_grade", sa.String(40)),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_courses_user_id", "courses", ["user_id"])
    op.create_index("ix_courses_deleted_at", "courses", ["deleted_at"])
    op.execute(
        sa.text(
            "INSERT INTO users (id, display_name) VALUES (:id, :name)"
        ).bindparams(id=DEVELOPMENT_USER_ID, name="Local Student")
    )


def downgrade() -> None:
    op.drop_table("courses")
    op.drop_table("users")

