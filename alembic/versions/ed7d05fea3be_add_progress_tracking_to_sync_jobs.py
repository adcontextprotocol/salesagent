"""Add progress tracking to sync_jobs

Revision ID: ed7d05fea3be
Revises: 1a7693edad5d
Create Date: 2025-10-19 06:43:06.718520

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ed7d05fea3be"
down_revision: str | Sequence[str] | None = "661c474053fa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add progress column to sync_jobs table
    op.add_column("sync_jobs", sa.Column("progress", sa.dialects.postgresql.JSONB, nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove progress column from sync_jobs table
    op.drop_column("sync_jobs", "progress")
