"""add adcp product fields

Revision ID: 021_add_adcp_product_fields
Revises: 020_fix_tasks_schema_properly
Create Date: 2025-09-02 17:20:00.000000

This migration was expected by production but missing from fix-prod branch.
Creating as a stub migration to fix the broken chain.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "021_add_adcp_product_fields"
down_revision: Union[str, Sequence[str], None] = "020_fix_tasks_schema_properly"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Stub upgrade - no changes needed.

    This migration exists only to fix the broken alembic chain.
    The actual AdCP v2.4 product fields were already added in previous migrations.
    """
    print("Migration 021 completed (stub migration)")


def downgrade() -> None:
    """Stub downgrade - no changes needed."""
    print("Migration 021 downgrade completed (stub migration)")
