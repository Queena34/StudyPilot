"""Add practice and feedback preferences to users.

Language and explanation-style preferences already existed on the user row but
were never exposed; these columns complete the settings surface PRD 8.6 requires.

Revision ID: 0008
Revises: 0007
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "default_question_type",
            sa.String(length=32),
            nullable=False,
            server_default="single_choice",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "default_difficulty", sa.String(length=16), nullable=False, server_default="medium"
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "default_question_count", sa.Integer(), nullable=False, server_default="5"
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "include_language_feedback",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    for column in (
        "include_language_feedback",
        "default_question_count",
        "default_difficulty",
        "default_question_type",
    ):
        op.drop_column("users", column)
