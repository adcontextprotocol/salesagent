"""add_gin_indexes_for_property_tags

Revision ID: ab57bdcf4bd8
Revises: eef85c5fe627
Create Date: 2025-10-13 10:11:20.268637

Add GIN indexes for JSONB property_tags columns to optimize queries that filter
products by property tags. This is critical for performance with large product catalogs.

Example query that benefits:
  SELECT * FROM products WHERE property_tags @> '["premium_sports"]'::jsonb
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ab57bdcf4bd8'
down_revision: Union[str, Sequence[str], None] = 'eef85c5fe627'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add GIN indexes for JSONB property_tags queries."""
    # GIN index for property_tags array containment queries
    op.create_index(
        "idx_products_property_tags_gin",
        "products",
        ["property_tags"],
        postgresql_using="gin",
    )
    print("✅ Added GIN index for products.property_tags (optimizes tag-based filtering)")


def downgrade() -> None:
    """Remove GIN indexes."""
    op.drop_index("idx_products_property_tags_gin", table_name="products")
