"""Record how each document divides into sections.

Chapters were modelled as a number, which left material that titles its parts
without numbering them — a slide handout, for instance — with no structure at
all. Sections carry a title and an ordinal position instead.

Revision ID: 0010
Revises: 0009
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "sections_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("documents", "sections_json")
