"""add_creative_review_fields_to_tenant

Revision ID: 51ff03cbe186
Revises: e2d9b45ea2bc
Create Date: 2025-10-07 10:09:53.934556

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "51ff03cbe186"
down_revision: str | Sequence[str] | None = "e2d9b45ea2bc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add creative review fields to tenants table
    op.add_column("tenants", sa.Column("creative_review_criteria", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("gemini_api_key", sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove creative review fields from tenants table
    op.drop_column("tenants", "gemini_api_key")
    op.drop_column("tenants", "creative_review_criteria")
