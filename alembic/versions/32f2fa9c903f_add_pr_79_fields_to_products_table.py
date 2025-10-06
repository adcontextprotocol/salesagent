"""AdCP PR #79: Placeholder migration (replaced by dynamic pricing)

Revision ID: 32f2fa9c903f
Revises: fc694918df34
Create Date: 2025-10-01 04:17:11.604374

Originally intended to add static PR #79 fields, but replaced with dynamic
pricing from cached historical reporting data. See migration 574ecf3d98c7 for
product_performance_metrics table that provides these values dynamically.

This migration is kept as a placeholder to maintain migration chain integrity.
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "32f2fa9c903f"
down_revision: str | Sequence[str] | None = "fc694918df34"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No-op: Static PR #79 fields replaced by dynamic pricing."""
    pass


def downgrade() -> None:
    """No-op: Static PR #79 fields never added."""
    pass
