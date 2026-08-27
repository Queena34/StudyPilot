"""Record the language of each document.

Retrieval matches a query against material in the material's own language, so
the language has to be known before a query is built.

Revision ID: 0009
Revises: 0008
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("language", sa.String(length=8), nullable=False, server_default="en"),
    )


def downgrade() -> None:
    op.drop_column("documents", "language")
