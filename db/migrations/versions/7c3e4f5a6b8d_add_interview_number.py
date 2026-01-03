"""Add interview_number field.

Revision ID: 7c3e4f5a6b8d
Revises: 5a8b2c9d1e4f
Create Date: 2026-01-02

Adds interview_number column to interviews table.
This is the ordinal number within a server (1, 2, 3, ...) rather than
the database primary key.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7c3e4f5a6b8d"
down_revision: str | None = "5a8b2c9d1e4f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add column as nullable first
    op.add_column(
        "interviews",
        sa.Column("interview_number", sa.Integer(), nullable=True),
    )

    # Populate existing rows with their ordinal within each server
    # Uses a window function to assign row numbers per server ordered by id
    op.execute(
        """
        UPDATE interviews
        SET interview_number = subq.row_num
        FROM (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY server_id ORDER BY id) as row_num
            FROM interviews
        ) subq
        WHERE interviews.id = subq.id
        """
    )

    # Make column NOT NULL
    op.alter_column("interviews", "interview_number", nullable=False)


def downgrade() -> None:
    op.drop_column("interviews", "interview_number")
