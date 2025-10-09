"""add_approval_mode_to_tenants

Revision ID: 4bec915209d1
Revises: 51ff03cbe186
Create Date: 2025-10-08 06:04:51.199311

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4bec915209d1"
down_revision: str | Sequence[str] | None = "51ff03cbe186"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add approval_mode column to tenants table
    # Default to 'require-human' for safety (existing tenants require human approval)
    op.add_column("tenants", sa.Column("approval_mode", sa.String(50), nullable=False, server_default="require-human"))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove approval_mode column
    op.drop_column("tenants", "approval_mode")
