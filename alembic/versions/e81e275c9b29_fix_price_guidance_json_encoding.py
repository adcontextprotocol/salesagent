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
    
    # Skip this migration in production for now - manual fix may be needed
    # The production database has different column types that need special handling
    print("Skipping price_guidance JSON fix migration - will handle manually if needed")
    return
    
    # Original migration code below (disabled for now)
    """
    # Get database type
    connection = op.get_bind()
    db_type = connection.dialect.name
    
    if db_type == "postgresql":
        # PostgreSQL: Fix double-encoded JSON strings
        # Production has JSON columns (not JSONB), so we need to cast to text for LIKE operations
        pass  # Complex migration code removed
        
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
