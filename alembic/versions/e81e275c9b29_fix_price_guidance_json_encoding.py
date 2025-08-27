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

    # Get database type
    connection = op.get_bind()
    db_type = connection.dialect.name

    if db_type == "postgresql":
        # PostgreSQL: Convert JSON strings back to proper JSON objects
        # This handles cases where the JSON was stored as a string instead of an object
        op.execute(
            """
            UPDATE products
            SET price_guidance = price_guidance::text::jsonb
            WHERE price_guidance IS NOT NULL
              AND jsonb_typeof(price_guidance) = 'string'
        """
        )

        # Also fix formats, targeting_template, and implementation_config if needed
        op.execute(
            """
            UPDATE products
            SET formats = formats::text::jsonb
            WHERE formats IS NOT NULL
              AND jsonb_typeof(formats) = 'string'
        """
        )

        op.execute(
            """
            UPDATE products
            SET targeting_template = targeting_template::text::jsonb
            WHERE targeting_template IS NOT NULL
              AND jsonb_typeof(targeting_template) = 'string'
        """
        )

        op.execute(
            """
            UPDATE products
            SET implementation_config = implementation_config::text::jsonb
            WHERE implementation_config IS NOT NULL
              AND jsonb_typeof(implementation_config) = 'string'
        """
        )

    elif db_type == "sqlite":
        # SQLite: Parse and re-encode JSON strings
        # SQLite stores JSON as text, so we need to handle double-encoded strings
        import json

        # Get all products with potentially double-encoded JSON
        result = connection.execute(
            sa.text(
                "SELECT product_id, tenant_id, price_guidance, formats, targeting_template, implementation_config FROM products"
            )
        )

        for row in result:
            updates = {}

            # Access row data by index
            product_id = row[0]
            tenant_id = row[1]
            price_guidance = row[2]
            formats = row[3]
            targeting_template = row[4]
            implementation_config = row[5]

            # Check and fix each JSON field
            fields_data = {
                "price_guidance": price_guidance,
                "formats": formats,
                "targeting_template": targeting_template,
                "implementation_config": implementation_config,
            }

            for field, value in fields_data.items():
                if value and isinstance(value, str):
                    try:
                        # Try to parse as JSON
                        parsed = json.loads(value)
                        # If it's a string, it might be double-encoded
                        if isinstance(parsed, str):
                            try:
                                # Parse again to get the actual object
                                parsed = json.loads(parsed)
                                updates[field] = json.dumps(parsed)
                            except json.JSONDecodeError:
                                pass
                    except json.JSONDecodeError:
                        pass

            # Apply updates if any
            if updates:
                set_clause = ", ".join([f"{k} = :{k}" for k in updates.keys()])
                params = {**updates, "product_id": product_id, "tenant_id": tenant_id}
                connection.execute(
                    sa.text(
                        f"UPDATE products SET {set_clause} WHERE product_id = :product_id AND tenant_id = :tenant_id"
                    ),
                    params,
                )


def downgrade() -> None:
    """Revert the JSON fix (not recommended)."""
    # Downgrade would re-introduce the bug, so we leave it as a no-op
    pass
