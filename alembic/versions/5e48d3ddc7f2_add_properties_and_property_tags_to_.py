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

# revision identifiers, used by Alembic.
revision: str = "5e48d3ddc7f2"
down_revision: str | Sequence[str] | None = "9309ac2fa74f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add properties and property_tags columns to products table, then backfill existing products."""
    # Step 1: Add properties column (JSONB array of Property objects)
    op.add_column("products", sa.Column("properties", sa.JSON(), nullable=True))

    # Step 2: Add property_tags column (JSONB array of strings)
    op.add_column("products", sa.Column("property_tags", sa.JSON(), nullable=True))

    # Step 3: Backfill existing products with default property_tags
    # This ensures all products have at least one of properties/property_tags
    # Use raw SQL to handle both PostgreSQL JSONB and potential SQLite JSON
    connection = op.get_bind()

    # Check if we're using PostgreSQL or SQLite
    dialect_name = connection.dialect.name

    if dialect_name == "postgresql":
        # PostgreSQL: Use JSONB array syntax
        connection.execute(
            sa.text(
                """
                UPDATE products
                SET property_tags = '["all_inventory"]'::jsonb
                WHERE property_tags IS NULL
                  AND properties IS NULL
            """
            )
        )
    else:
        # SQLite: Use JSON string syntax
        connection.execute(
            sa.text(
                """
                UPDATE products
                SET property_tags = '["all_inventory"]'
                WHERE property_tags IS NULL
                  AND properties IS NULL
            """
            )
        )

    # Log the migration
    print(f"✅ Added property authorization fields to products table ({dialect_name})")
    print("📋 Backfilled existing products with property_tags=['all_inventory']")


def downgrade() -> None:
    """Remove properties and property_tags columns from products table."""
    op.drop_column("products", "property_tags")
    op.drop_column("products", "properties")
