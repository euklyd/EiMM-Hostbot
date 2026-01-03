"""Add server_id to votes, make interview_id optional.

Revision ID: 5a8b2c9d1e4f
Revises: 3d70d80ef3b1
Create Date: 2026-01-02

Changes votes to be per-server instead of per-interview:
- Add server_id column (required)
- Make interview_id optional (for historical tracking)
- Change unique constraint from (interview_id, voter_id, candidate_id)
  to (server_id, voter_id, candidate_id)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5a8b2c9d1e4f"
down_revision: str | None = "3d70d80ef3b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add server_id column (nullable first for data migration)
    op.add_column(
        "interview_votes",
        sa.Column("server_id", sa.BigInteger(), nullable=True),
    )

    # Populate server_id from interviews table
    op.execute(
        """
        UPDATE interview_votes
        SET server_id = (
            SELECT server_id FROM interviews
            WHERE interviews.id = interview_votes.interview_id
        )
        """
    )

    # Delete any orphaned votes (shouldn't exist but be safe)
    op.execute("DELETE FROM interview_votes WHERE server_id IS NULL")

    # Make server_id NOT NULL
    op.alter_column("interview_votes", "server_id", nullable=False)

    # Add FK constraint for server_id
    op.create_foreign_key(
        "fk_interview_votes_server_id",
        "interview_votes",
        "interview_servers",
        ["server_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Make interview_id nullable
    op.alter_column("interview_votes", "interview_id", nullable=True)

    # Drop old FK constraint and unique constraint
    # Need to drop index first, then constraints
    op.drop_index("ix_interview_votes_interview_id", table_name="interview_votes")
    op.drop_constraint(
        "interview_votes_interview_id_voter_id_candidate_id_key",
        "interview_votes",
        type_="unique",
    )
    op.drop_constraint(
        "interview_votes_interview_id_fkey", "interview_votes", type_="foreignkey"
    )

    # Add new FK for interview_id with SET NULL on delete
    op.create_foreign_key(
        "fk_interview_votes_interview_id",
        "interview_votes",
        "interviews",
        ["interview_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Add new unique constraint on server_id
    op.create_unique_constraint(
        "uq_interview_votes_server_voter_candidate",
        "interview_votes",
        ["server_id", "voter_id", "candidate_id"],
    )

    # Add index on server_id
    op.create_index(
        "ix_interview_votes_server_id", "interview_votes", ["server_id"]
    )


def downgrade() -> None:
    # This downgrade will fail if there are any votes without interview_id
    # since we're making it NOT NULL again

    # Drop new constraints
    op.drop_index("ix_interview_votes_server_id", table_name="interview_votes")
    op.drop_constraint(
        "uq_interview_votes_server_voter_candidate", "interview_votes", type_="unique"
    )
    op.drop_constraint(
        "fk_interview_votes_interview_id", "interview_votes", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_interview_votes_server_id", "interview_votes", type_="foreignkey"
    )

    # Delete votes without interview_id (can't restore these)
    op.execute("DELETE FROM interview_votes WHERE interview_id IS NULL")

    # Make interview_id NOT NULL again
    op.alter_column("interview_votes", "interview_id", nullable=False)

    # Drop server_id column
    op.drop_column("interview_votes", "server_id")

    # Restore original FK and constraints
    op.create_foreign_key(
        "interview_votes_interview_id_fkey",
        "interview_votes",
        "interviews",
        ["interview_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "interview_votes_interview_id_voter_id_candidate_id_key",
        "interview_votes",
        ["interview_id", "voter_id", "candidate_id"],
    )
    op.create_index(
        "ix_interview_votes_interview_id", "interview_votes", ["interview_id"]
    )
