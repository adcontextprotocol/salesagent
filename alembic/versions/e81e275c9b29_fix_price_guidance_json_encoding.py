"""fix_price_guidance_json_encoding

Revision ID: e81e275c9b29
Revises: 2485bb2ff253
Create Date: 2025-08-26 23:14:40.002149

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e81e275c9b29"
down_revision: Union[str, Sequence[str], None] = "2485bb2ff253"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fix JSON fields that were incorrectly double-encoded as strings."""

    import json
    from sqlalchemy import text

    # Get database connection
    connection = op.get_bind()

    # Detect database type
    dialect_name = connection.dialect.name

    if dialect_name == "postgresql":
        # PostgreSQL: Fix double-encoded JSON strings
        # First, let's check if we have any double-encoded data
        result = connection.execute(
            text(
                """
            SELECT COUNT(*) FROM products
            WHERE price_guidance IS NOT NULL
            AND price_guidance::text LIKE '"%'
        """
            )
        )
        count = result.scalar()

        if count and count > 0:
            print(f"Fixing {count} double-encoded price_guidance fields in PostgreSQL...")

            # Fix price_guidance
            connection.execute(
                text(
                    """
                UPDATE products
                SET price_guidance = (price_guidance #>> '{}')::jsonb
                WHERE price_guidance IS NOT NULL
                AND price_guidance::text LIKE '"%'
            """
                )
            )

            # Fix formats
            connection.execute(
                text(
                    """
                UPDATE products
                SET formats = (formats #>> '{}')::jsonb
                WHERE formats IS NOT NULL
                AND formats::text LIKE '["%' OR formats::text LIKE '{"%'
            """
                )
            )

            # Fix targeting_template
            connection.execute(
                text(
                    """
                UPDATE products
                SET targeting_template = (targeting_template #>> '{}')::jsonb
                WHERE targeting_template IS NOT NULL
                AND targeting_template::text LIKE '{"%'
            """
                )
            )

            # Fix implementation_config
            connection.execute(
                text(
                    """
                UPDATE products
                SET implementation_config = (implementation_config #>> '{}')::jsonb
                WHERE implementation_config IS NOT NULL
                AND implementation_config::text LIKE '{"%'
            """
                )
            )

            print("PostgreSQL JSON fields fixed successfully")
        else:
            print("No double-encoded JSON fields found in PostgreSQL - skipping")

    elif dialect_name == "sqlite":
        # SQLite: Parse and re-encode JSON strings
        # Get all products with potential double-encoded JSON
        result = connection.execute(
            text(
                """
            SELECT product_id, price_guidance, formats, targeting_template, implementation_config
            FROM products
            WHERE price_guidance IS NOT NULL OR formats IS NOT NULL
            OR targeting_template IS NOT NULL OR implementation_config IS NOT NULL
        """
            )
        )

        products_to_fix = []
        for row in result:
            product_id = row[0]
            needs_fix = False
            fixed_values = {}

            # Check each JSON field
            for idx, field_name in enumerate(
                ["price_guidance", "formats", "targeting_template", "implementation_config"], start=1
            ):
                field_value = row[idx]
                if field_value and isinstance(field_value, str):
                    # Try to detect double-encoded JSON
                    if field_value.startswith('"{') or field_value.startswith('"['):
                        try:
                            # First parse to get the JSON string
                            json_str = json.loads(field_value)
                            # Then parse the actual JSON
                            actual_value = json.loads(json_str) if isinstance(json_str, str) else json_str
                            fixed_values[field_name] = json.dumps(actual_value)
                            needs_fix = True
                        except (json.JSONDecodeError, TypeError):
                            # Not double-encoded or corrupt, skip
                            pass

            if needs_fix:
                products_to_fix.append((product_id, fixed_values))

        # Apply fixes
        if products_to_fix:
            print(f"Fixing {len(products_to_fix)} products with double-encoded JSON fields in SQLite...")
            for product_id, fixed_values in products_to_fix:
                for field_name, fixed_value in fixed_values.items():
                    connection.execute(
                        text(f"UPDATE products SET {field_name} = :value WHERE product_id = :product_id"),
                        {"value": fixed_value, "product_id": product_id},
                    )
            print("SQLite JSON fields fixed successfully")
        else:
            print("No double-encoded JSON fields found in SQLite - skipping")


def downgrade() -> None:
    """Revert the JSON fix (not recommended)."""
    # Downgrade would re-introduce the bug, so we leave it as a no-op
    pass
