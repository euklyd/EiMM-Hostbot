"""Add pg_trgm extension and search indexes.

Revision ID: 9f1a2b3c4d5e
Revises: 7c3e4f5a6b8d
Create Date: 2026-01-11

Adds pg_trgm extension for fuzzy text search and GIN indexes on
question_text and answer_text columns.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "9f1a2b3c4d5e"
down_revision: str | None = "7c3e4f5a6b8d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Enable pg_trgm extension for fuzzy text search
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # GIN indexes for fuzzy text search on question content
    op.execute(
        """
        CREATE INDEX ix_interview_questions_question_text_trgm
        ON interview_questions
        USING gin (question_text gin_trgm_ops)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_interview_questions_answer_text_trgm
        ON interview_questions
        USING gin (answer_text gin_trgm_ops)
        WHERE answer_text IS NOT NULL
        """
    )

    # btree indexes for exact/prefix search on names and dates
    op.create_index(
        "ix_interview_questions_asker_name",
        "interview_questions",
        ["asker_name"],
    )
    op.create_index(
        "ix_interview_questions_asked_at",
        "interview_questions",
        ["asked_at"],
    )
    op.create_index(
        "ix_interviews_interviewee_name",
        "interviews",
        ["interviewee_name"],
    )


def downgrade() -> None:
    # Drop btree indexes
    op.drop_index("ix_interviews_interviewee_name", table_name="interviews")
    op.drop_index("ix_interview_questions_asked_at", table_name="interview_questions")
    op.drop_index("ix_interview_questions_asker_name", table_name="interview_questions")

    # Drop GIN indexes
    op.execute("DROP INDEX IF EXISTS ix_interview_questions_answer_text_trgm")
    op.execute("DROP INDEX IF EXISTS ix_interview_questions_question_text_trgm")

    # Note: We don't drop the pg_trgm extension as it might be used elsewhere
