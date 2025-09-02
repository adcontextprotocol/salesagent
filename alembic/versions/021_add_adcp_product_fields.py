"""Add AdCP v2.5 product fields (min_spend, measurement, creative_policy)

Revision ID: 021_add_adcp_product_fields
Revises: 020_fix_tasks_schema_properly
Create Date: 2025-09-02 07:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "021_add_adcp_product_fields"
down_revision: Union[str, Sequence[str], None] = "020_fix_tasks_schema_properly"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add missing AdCP product fields safely."""
    # Check if columns already exist to make migration idempotent
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = [col["name"] for col in inspector.get_columns("products")]

    # Add min_spend column if it doesn't exist
    if "min_spend" not in existing_columns:
        op.add_column(
            "products",
            sa.Column("min_spend", sa.DECIMAL(10, 2), nullable=True, comment="Minimum spend requirement per AdCP v2.5"),
        )
        print("✅ Added min_spend column to products table")
    else:
        print("ℹ️  min_spend column already exists, skipping")

    # Add measurement column if it doesn't exist
    if "measurement" not in existing_columns:
        # Use appropriate JSON type for database
        json_type = postgresql.JSONB() if conn.dialect.name == "postgresql" else sa.JSON()
        op.add_column(
            "products",
            sa.Column("measurement", json_type, nullable=True, comment="AdCP measurement configuration object"),
        )
        print("✅ Added measurement column to products table")
    else:
        print("ℹ️  measurement column already exists, skipping")

    # Add creative_policy column if it doesn't exist
    if "creative_policy" not in existing_columns:
        # Use appropriate JSON type for database
        json_type = postgresql.JSONB() if conn.dialect.name == "postgresql" else sa.JSON()
        op.add_column(
            "products",
            sa.Column("creative_policy", json_type, nullable=True, comment="AdCP creative policy configuration"),
        )
        print("✅ Added creative_policy column to products table")
    else:
        print("ℹ️  creative_policy column already exists, skipping")


def downgrade() -> None:
    """Remove the AdCP product fields."""
    # Check if columns exist before dropping to make downgrade idempotent
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = [col["name"] for col in inspector.get_columns("products")]

    # Remove columns if they exist
    if "creative_policy" in existing_columns:
        op.drop_column("products", "creative_policy")
        print("✅ Removed creative_policy column from products table")

    if "measurement" in existing_columns:
        op.drop_column("products", "measurement")
        print("✅ Removed measurement column from products table")

    if "min_spend" in existing_columns:
        op.drop_column("products", "min_spend")
        print("✅ Removed min_spend column from products table")
