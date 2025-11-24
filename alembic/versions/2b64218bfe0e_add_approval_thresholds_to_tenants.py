"""add_approval_thresholds_to_tenants

Revision ID: 2b64218bfe0e
Revises: 3709c99944e5
Create Date: 2025-11-24 14:04:02.419056

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2b64218bfe0e"
down_revision: Union[str, Sequence[str], None] = "445171389125"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add creative_auto_approve_threshold column with default value 0.9
    op.add_column(
        "tenants", sa.Column("creative_auto_approve_threshold", sa.Float(), nullable=False, server_default="0.9")
    )

    # Add creative_auto_reject_threshold column with default value 0.1
    op.add_column(
        "tenants", sa.Column("creative_auto_reject_threshold", sa.Float(), nullable=False, server_default="0.1")
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Remove creative_auto_reject_threshold column
    op.drop_column("tenants", "creative_auto_reject_threshold")

    # Remove creative_auto_approve_threshold column
    op.drop_column("tenants", "creative_auto_approve_threshold")
