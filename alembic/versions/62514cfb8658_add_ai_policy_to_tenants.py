"""add_ai_policy_to_tenants

Revision ID: 62514cfb8658
Revises: bb73ab14a5d2
Create Date: 2025-10-08 16:07:14.275978

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from src.core.database.json_type import JSONType

# revision identifiers, used by Alembic.
revision: str = "62514cfb8658"
down_revision: str | Sequence[str] | None = "bb73ab14a5d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ai_policy column to tenants table for confidence-based AI review configuration."""
    op.add_column(
        "tenants",
        sa.Column(
            "ai_policy", JSONType(), nullable=True, comment="AI review policy configuration with confidence thresholds"
        ),
    )


def downgrade() -> None:
    """Remove ai_policy column from tenants table."""
    op.drop_column("tenants", "ai_policy")
