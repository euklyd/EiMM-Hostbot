"""Initial interview schema.

Revision ID: 3d70d80ef3b1
Revises:
Create Date: 2026-01-02

Creates the interview cog tables:
- interview_servers: Server-level configuration
- interviews: Interview sessions
- interview_questions: Questions and answers
- interview_votes: Votes for next interviewee
- interview_opt_outs: Users who opted out
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3d70d80ef3b1"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Interview servers (guild configuration)
    op.create_table(
        "interview_servers",
        sa.Column("id", sa.BigInteger(), nullable=False, comment="Discord guild ID"),
        sa.Column("name", sa.String(100), nullable=False),
        # Channel configuration
        sa.Column("answer_channel_id", sa.BigInteger(), nullable=True),
        sa.Column("backstage_channel_id", sa.BigInteger(), nullable=True),
        sa.Column("voting_channel_id", sa.BigInteger(), nullable=True),
        # Role configuration
        sa.Column("manager_role_id", sa.BigInteger(), nullable=True),
        sa.Column("audience_role_id", sa.BigInteger(), nullable=True),
        # Interview settings
        sa.Column(
            "default_question",
            sa.Text(),
            nullable=False,
            server_default="What's your favorite card?",
        ),
        sa.Column("reinterview_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reinterviews_allowed", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="false"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Interviews
    op.create_table(
        "interviews",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("server_id", sa.BigInteger(), nullable=False),
        # Interviewee info
        sa.Column("interviewee_id", sa.BigInteger(), nullable=False),
        sa.Column("interviewee_name", sa.String(100), nullable=False),
        # Timing
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        # OP message
        sa.Column("op_channel_id", sa.BigInteger(), nullable=True),
        sa.Column("op_message_id", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["server_id"],
            ["interview_servers.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_interviews_server_id", "interviews", ["server_id"])

    # Questions
    op.create_table(
        "interview_questions",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("interview_id", sa.Integer(), nullable=False),
        sa.Column("question_number", sa.Integer(), nullable=False),
        # Asker info
        sa.Column("asker_id", sa.BigInteger(), nullable=False),
        sa.Column("asker_name", sa.String(100), nullable=False),
        # Content
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=True),
        # Status
        sa.Column("is_posted", sa.Boolean(), nullable=False, server_default="false"),
        # Timestamps
        sa.Column(
            "asked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        # Source message
        sa.Column("source_guild_id", sa.BigInteger(), nullable=False),
        sa.Column("source_channel_id", sa.BigInteger(), nullable=False),
        sa.Column("source_message_id", sa.BigInteger(), nullable=False),
        # Posted message
        sa.Column("posted_message_id", sa.BigInteger(), nullable=True),
        # Soft delete for moderation
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["interview_id"],
            ["interviews.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_interview_questions_interview_id", "interview_questions", ["interview_id"])

    # Votes
    op.create_table(
        "interview_votes",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("interview_id", sa.Integer(), nullable=False),
        sa.Column("voter_id", sa.BigInteger(), nullable=False),
        sa.Column("candidate_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "voted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["interview_id"],
            ["interviews.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("interview_id", "voter_id", "candidate_id"),
    )
    op.create_index("ix_interview_votes_interview_id", "interview_votes", ["interview_id"])

    # Opt-outs
    op.create_table(
        "interview_opt_outs",
        sa.Column("server_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("server_id", "user_id"),
        sa.ForeignKeyConstraint(
            ["server_id"],
            ["interview_servers.id"],
            ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    op.drop_table("interview_opt_outs")
    op.drop_table("interview_votes")
    op.drop_table("interview_questions")
    op.drop_table("interviews")
    op.drop_table("interview_servers")
