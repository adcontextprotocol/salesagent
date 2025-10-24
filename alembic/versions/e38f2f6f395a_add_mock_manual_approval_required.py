"""add_mock_manual_approval_required

Revision ID: e38f2f6f395a
Revises: faaed3b71428
Create Date: 2025-10-23 20:06:20.766732

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e38f2f6f395a"
down_revision: str | Sequence[str] | None = "faaed3b71428"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add mock_manual_approval_required column to adapter_config table
    op.add_column("adapter_config", sa.Column("mock_manual_approval_required", sa.Boolean(), nullable=True))

    # Set default value to False for ALL existing rows (not just mock adapters)
    op.execute("UPDATE adapter_config SET mock_manual_approval_required = false")

    # Make the column non-nullable after setting defaults
    op.alter_column("adapter_config", "mock_manual_approval_required", nullable=False, server_default=sa.false())


def downgrade() -> None:
    """Downgrade schema."""
    # Remove mock_manual_approval_required column
    op.drop_column("adapter_config", "mock_manual_approval_required")
