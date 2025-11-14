"""Add gam_axe_custom_targeting_key to adapter_config

Revision ID: 986aa36f9589
Revises: 039d59477ab4
Create Date: 2025-11-13 12:16:09.820196

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "986aa36f9589"
down_revision: Union[str, Sequence[str], None] = "039d59477ab4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add gam_axe_custom_targeting_key column to adapter_config table
    op.add_column(
        "adapter_config",
        sa.Column(
            "gam_axe_custom_targeting_key",
            sa.String(length=100),
            nullable=True,
            server_default="axe_segment",
            comment="GAM custom targeting key name for AXE segment targeting (AdCP 3.0.3 axe_include_segment/axe_exclude_segment)",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Remove gam_axe_custom_targeting_key column from adapter_config table
    op.drop_column("adapter_config", "gam_axe_custom_targeting_key")
