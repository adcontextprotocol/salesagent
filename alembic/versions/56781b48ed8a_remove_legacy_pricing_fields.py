"""remove_legacy_pricing_fields

Remove legacy pricing fields from products table now that all data has been
migrated to pricing_options table.

Removes:
- is_fixed_price (boolean)
- cpm (numeric)
- price_guidance (jsonb)
- currency (text)
- delivery_type (text) - derived from pricing_options

Revision ID: 56781b48ed8a
Revises: 5d949a78d36f
Create Date: 2025-10-13 01:48:29.611034

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '56781b48ed8a'
down_revision: Union[str, Sequence[str], None] = '5d949a78d36f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove legacy pricing fields from products table."""
    # Drop legacy pricing columns
    op.drop_column('products', 'is_fixed_price')
    op.drop_column('products', 'cpm')
    op.drop_column('products', 'price_guidance')
    op.drop_column('products', 'currency')
    op.drop_column('products', 'delivery_type')

    print("✅ Removed legacy pricing fields from products table")


def downgrade() -> None:
    """Restore legacy pricing fields (empty, for rollback only)."""
    # Add columns back (but data will be lost)
    op.add_column('products', sa.Column('delivery_type', sa.Text(), nullable=True))
    op.add_column('products', sa.Column('currency', sa.Text(), nullable=True))
    op.add_column('products', sa.Column('price_guidance', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('products', sa.Column('cpm', sa.Numeric(), nullable=True))
    op.add_column('products', sa.Column('is_fixed_price', sa.Boolean(), nullable=True))

    print("⚠️  Restored legacy pricing columns (but data was not recovered)")
