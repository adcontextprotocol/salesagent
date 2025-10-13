"""add_gin_indexes_for_property_tags

Revision ID: ab57bdcf4bd8
Revises: 1aa2f5893a4d
Create Date: 2025-10-13 10:11:20.268637

Add GIN indexes for JSONB property_tags columns to optimize queries that filter
products by property tags. This is critical for performance with large product catalogs.

IMPORTANT: This migration must run AFTER 1aa2f5893a4d (TEXT to JSONB conversion).
          property_tags must be native JSONB before creating GIN index.

Example query that benefits:
  SELECT * FROM products WHERE property_tags @> '["premium_sports"]'::jsonb

Performance impact:
  - Without index: Sequential scan O(n)
  - With GIN index: Index scan O(log n)
  - Especially important for catalogs with 1000+ products
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ab57bdcf4bd8'
down_revision: Union[str, Sequence[str], None] = '1aa2f5893a4d'  # Must run after JSONB conversion
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add GIN indexes for native JSONB property_tags queries."""
    # Now that property_tags is native JSONB, we can create GIN index directly
    # No CAST needed - much cleaner and faster
    op.create_index(
        "idx_products_property_tags_gin",
        "products",
        ["property_tags"],
        postgresql_using="gin",
        postgresql_ops={"property_tags": "jsonb_path_ops"},  # Optimized for @> operator
    )
    print("✅ Added GIN index for products.property_tags (native JSONB, optimizes @> queries)")


def downgrade() -> None:
    """Remove GIN indexes."""
    op.drop_index("idx_products_property_tags_gin", table_name="products")
