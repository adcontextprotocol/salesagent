"""add_virtual_host_field_to_tenants

Revision ID: 4f80e016686e
Revises: 8f8c9aec1458
Create Date: 2025-09-14 11:06:16.215819

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4f80e016686e"
down_revision: str | Sequence[str] | None = "8f8c9aec1458"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add virtual_host field to tenants table for Approximated.app integration."""
    # Add virtual_host column to tenants table
    op.add_column("tenants", sa.Column("virtual_host", sa.Text, nullable=True))

    # Add unique index for virtual_host (null values are allowed but duplicates are not)
    op.create_index("ix_tenants_virtual_host", "tenants", ["virtual_host"], unique=True)


def downgrade() -> None:
    """Remove virtual_host field from tenants table."""
    # Drop the index first
    op.drop_index("ix_tenants_virtual_host", table_name="tenants")

    # Drop the column
    op.drop_column("tenants", "virtual_host")
