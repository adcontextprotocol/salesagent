"""Add properties and property_tags to products

Revision ID: 5e48d3ddc7f2
Revises: 9309ac2fa74f
Create Date: 2025-10-12 15:26:37.998545

This migration adds property authorization fields to products per AdCP spec.
Products must have either 'properties' (full Property objects) or 'property_tags'
(array of tag strings) to enable buyer authorization validation.

The migration also backfills existing products with default property_tags=['all_inventory'].
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from src.core.database.json_type import JSONType

# revision identifiers, used by Alembic.
revision: str = "5e48d3ddc7f2"
down_revision: str | Sequence[str] | None = "9309ac2fa74f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add properties and property_tags columns to products table, then backfill existing products."""
    # Step 1: Add properties column (JSONB array of Property objects)
    op.add_column("products", sa.Column("properties", JSONType, nullable=True))

    # Step 2: Add property_tags column (JSONB array of strings)
    op.add_column("products", sa.Column("property_tags", JSONType, nullable=True))

    # Step 3: Backfill existing products with default property_tags
    # This ensures all products have at least one of properties/property_tags
    # Uses SQLAlchemy Core for type-safe updates
    from sqlalchemy import and_, table, column, update

    # Define minimal table for update (no need for full model import)
    products_table = table(
        "products",
        column("property_tags", JSONType),
        column("properties", JSONType),
    )

    connection = op.get_bind()
    connection.execute(
        update(products_table)
        .where(and_(products_table.c.property_tags.is_(None), products_table.c.properties.is_(None)))
        .values(property_tags=["all_inventory"])
    )

    # Log the migration
    print("✅ Added property authorization fields to products table")
    print("📋 Backfilled existing products with property_tags=['all_inventory']")


def downgrade() -> None:
    """Remove properties and property_tags columns from products table."""
    op.drop_column("products", "property_tags")
    op.drop_column("products", "properties")
