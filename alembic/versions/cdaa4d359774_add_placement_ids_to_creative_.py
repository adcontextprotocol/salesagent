"""add_placement_ids_to_creative_assignments

Revision ID: cdaa4d359774
Revises: f3bac4654620
Create Date: 2026-01-01 16:15:50.697111

Adds placement_ids column to creative_assignments table for adcp#208 support.
This enables placement-specific targeting within packages when assigning creatives.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "cdaa4d359774"
down_revision: Union[str, Sequence[str], None] = "f3bac4654620"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add placement_ids column to creative_assignments."""
    op.add_column(
        "creative_assignments", sa.Column("placement_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )


def downgrade() -> None:
    """Remove placement_ids column from creative_assignments."""
    op.drop_column("creative_assignments", "placement_ids")
