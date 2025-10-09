"""Add creative review fields to tenants table

Revision ID: 8cce9697e412
Revises: cce7df2e7bea
Create Date: 2025-10-09 07:51:54.049754

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8cce9697e412"
down_revision: str | Sequence[str] | None = "cce7df2e7bea"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add creative review and AI policy fields to tenants table."""
    # Add creative_review_criteria column
    op.add_column("tenants", sa.Column("creative_review_criteria", sa.Text(), nullable=True))

    # Add approval_mode column with default
    op.add_column(
        "tenants", sa.Column("approval_mode", sa.String(length=50), nullable=False, server_default="require-human")
    )

    # Add ai_policy column (JSON/JSONB)
    op.add_column("tenants", sa.Column("ai_policy", sa.JSON(), nullable=True))

    # Add gemini_api_key column
    op.add_column("tenants", sa.Column("gemini_api_key", sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Remove creative review and AI policy fields from tenants table."""
    op.drop_column("tenants", "gemini_api_key")
    op.drop_column("tenants", "ai_policy")
    op.drop_column("tenants", "approval_mode")
    op.drop_column("tenants", "creative_review_criteria")
