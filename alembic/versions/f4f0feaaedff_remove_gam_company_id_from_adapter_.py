"""Remove gam_company_id from adapter_config (per-principal only)

Revision ID: f4f0feaaedff
Revises: fc694918df34
Create Date: 2025-10-03 21:38:22.059222

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f4f0feaaedff"
down_revision: str | Sequence[str] | None = "fc694918df34"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema: Remove gam_company_id column (now per-principal only)."""
    # Drop gam_company_id column - advertiser_id is per-principal in platform_mappings
    with op.batch_alter_table("adapter_config", schema=None) as batch_op:
        batch_op.drop_column("gam_company_id")


def downgrade() -> None:
    """Downgrade schema: Re-add gam_company_id column."""
    with op.batch_alter_table("adapter_config", schema=None) as batch_op:
        batch_op.add_column(sa.Column("gam_company_id", sa.String(50), nullable=True))
