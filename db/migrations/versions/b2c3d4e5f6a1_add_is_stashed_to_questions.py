"""Add is_stashed to interview_questions.

Revision ID: b2c3d4e5f6a1
Revises: 9f1a2b3c4d5e
Create Date: 2026-03-08

Allows questions to be stashed (excluded from batch posting) without
losing any answer text that may have been written.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a1"
down_revision: str | None = "9f1a2b3c4d5e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "interview_questions",
        sa.Column("is_stashed", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("interview_questions", "is_stashed")
