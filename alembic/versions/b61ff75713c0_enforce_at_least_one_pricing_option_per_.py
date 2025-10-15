"""enforce_at_least_one_pricing_option_per_product

Enforce data integrity: Every product MUST have at least one pricing option.

This migration:
1. Validates that all existing products have pricing options
2. Creates a trigger to prevent products from losing all pricing options

Revision ID: b61ff75713c0
Revises: 7426aa7e2f1a
Create Date: 2025-10-15 07:00:07.929952

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b61ff75713c0"
down_revision: str | Sequence[str] | None = "7426aa7e2f1a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Enforce at least one pricing option per product constraint."""

    # 1. Safety check: Verify all products have pricing_options
    connection = op.get_bind()
    result = connection.execute(
        sa.text(
            "SELECT p.product_id, p.tenant_id "
            "FROM products p "
            "LEFT JOIN pricing_options po ON p.tenant_id = po.tenant_id AND p.product_id = po.product_id "
            "WHERE po.id IS NULL"
        )
    )
    orphaned_products = result.fetchall()

    if orphaned_products:
        product_list = ", ".join([f"{row[0]} (tenant: {row[1]})" for row in orphaned_products[:5]])
        if len(orphaned_products) > 5:
            product_list += f" ... and {len(orphaned_products) - 5} more"

        raise ValueError(
            f"Cannot enforce pricing_options constraint - {len(orphaned_products)} products have no pricing_options. "
            f"All products MUST have at least one pricing option. "
            f"Affected products: {product_list}. "
            f"Fix: Create pricing_options for these products before running migration."
        )

    # 2. Create a trigger function to prevent deletion of last pricing option
    connection.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION prevent_empty_pricing_options()
            RETURNS TRIGGER AS $$
            DECLARE
                remaining_count INTEGER;
            BEGIN
                -- Check if this DELETE would leave the product with no pricing options
                SELECT COUNT(*) INTO remaining_count
                FROM pricing_options
                WHERE tenant_id = OLD.tenant_id
                  AND product_id = OLD.product_id
                  AND id != OLD.id;

                IF remaining_count = 0 THEN
                    RAISE EXCEPTION 'Cannot delete last pricing option for product % (tenant %). Every product must have at least one pricing option.',
                        OLD.product_id, OLD.tenant_id;
                END IF;

                RETURN OLD;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )

    # 3. Create trigger on pricing_options DELETE
    connection.execute(
        sa.text(
            """
            CREATE TRIGGER enforce_min_one_pricing_option
            BEFORE DELETE ON pricing_options
            FOR EACH ROW
            EXECUTE FUNCTION prevent_empty_pricing_options();
            """
        )
    )


def downgrade() -> None:
    """Remove pricing option constraint enforcement."""
    connection = op.get_bind()

    # Drop trigger
    connection.execute(sa.text("DROP TRIGGER IF EXISTS enforce_min_one_pricing_option ON pricing_options;"))

    # Drop function
    connection.execute(sa.text("DROP FUNCTION IF EXISTS prevent_empty_pricing_options();"))
