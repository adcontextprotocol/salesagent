"""add_brand_manifest_policy_to_tenants

Revision ID: 3709c99944e5
Revises: 445171389125
Create Date: 2025-11-24 14:02:24.375072

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3709c99944e5"
down_revision: Union[str, Sequence[str], None] = "445171389125"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add brand_manifest_policy column with default value "public"
    op.add_column(
        "tenants", sa.Column("brand_manifest_policy", sa.String(length=50), nullable=False, server_default="public")
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Remove brand_manifest_policy column
    op.drop_column("tenants", "brand_manifest_policy")
