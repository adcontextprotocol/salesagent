"""add_landing_page_config_and_product_visibility

Revision ID: f7e503a712cf
Revises: 4f80e016686e
Create Date: 2025-09-17 06:57:31.472360

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7e503a712cf"
down_revision: str | Sequence[str] | None = "4f80e016686e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add landing page configuration and product visibility controls."""
    # Add landing_config column to tenants table for landing page customization
    op.add_column("tenants", sa.Column("landing_config", sa.JSON, nullable=True))

    # Add requires_authentication column to products table for visibility control
    op.add_column("products", sa.Column("requires_authentication", sa.Boolean, nullable=False, server_default="false"))


def downgrade() -> None:
    """Remove landing page configuration and product visibility controls."""
    # Remove columns in reverse order
    op.drop_column("products", "requires_authentication")
    op.drop_column("tenants", "landing_config")
