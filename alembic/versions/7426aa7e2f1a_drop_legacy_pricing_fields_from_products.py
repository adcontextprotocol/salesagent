"""drop_legacy_pricing_fields_from_products

Revision ID: 7426aa7e2f1a
Revises: 7a33a9be8c6c
Create Date: 2025-10-14 21:25:00.754892

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7426aa7e2f1a"
down_revision: str | Sequence[str] | None = "7a33a9be8c6c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop legacy pricing fields from products table.

    All products now use pricing_options table exclusively.
    Legacy fields being dropped:
    - is_fixed_price (Boolean)
    - cpm (DECIMAL)
    - min_spend (DECIMAL)
    - currency (String) - legacy version, product currency is now in pricing_options
    """
    # Drop legacy pricing columns
    op.drop_column("products", "is_fixed_price")
    op.drop_column("products", "cpm")
    op.drop_column("products", "min_spend")
    op.drop_column("products", "currency")


def downgrade() -> None:
    """Restore legacy pricing fields (for rollback only - not recommended).

    WARNING: This will restore the columns but they will be empty.
    You would need to manually migrate data from pricing_options back to these fields.
    """

    # Restore legacy columns
    op.add_column("products", sa.Column("is_fixed_price", sa.Boolean(), nullable=True))
    op.add_column("products", sa.Column("cpm", sa.DECIMAL(precision=10, scale=2), nullable=True))
    op.add_column("products", sa.Column("min_spend", sa.DECIMAL(precision=10, scale=2), nullable=True))
    op.add_column("products", sa.Column("currency", sa.String(length=3), nullable=True))
