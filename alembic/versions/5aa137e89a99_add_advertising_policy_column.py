"""add_advertising_policy_column

Revision ID: 5aa137e89a99
Revises: 2a2aaed3b50d
Create Date: 2025-10-13 21:26:24.694687

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5aa137e89a99"
down_revision: str | Sequence[str] | None = "2a2aaed3b50d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add advertising_policy column to tenants table
    op.add_column(
        "tenants",
        sa.Column(
            "advertising_policy",
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Advertising policy configuration with prohibited categories, tactics, and advertisers",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Remove advertising_policy column from tenants table
    op.drop_column("tenants", "advertising_policy")
