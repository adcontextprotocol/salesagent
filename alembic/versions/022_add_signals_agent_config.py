"""Add signals_agent_config column to tenants table for upstream signals discovery

Revision ID: 022_add_signals_agent_config
Revises: 021_add_adcp_product_fields
Create Date: 2025-09-03 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "022_add_signals_agent_config"
down_revision: str | Sequence[str] | None = "021_add_adcp_product_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add signals_agent_config column to tenants table."""
    # Check if column already exists to make migration idempotent
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = [col["name"] for col in inspector.get_columns("tenants")]

    # Add signals_agent_config column if it doesn't exist
    if "signals_agent_config" not in existing_columns:
        # Use appropriate JSON type for database
        json_type = postgresql.JSONB() if conn.dialect.name == "postgresql" else sa.JSON()
        op.add_column(
            "tenants",
            sa.Column(
                "signals_agent_config",
                json_type,
                nullable=True,
                comment="Configuration for upstream AdCP signals discovery agent",
            ),
        )
        print("✅ Added signals_agent_config column to tenants table")
    else:
        print("ℹ️  signals_agent_config column already exists, skipping")


def downgrade() -> None:
    """Remove signals_agent_config column from tenants table."""
    # Check if column exists before dropping to make downgrade idempotent
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = [col["name"] for col in inspector.get_columns("tenants")]

    # Remove column if it exists
    if "signals_agent_config" in existing_columns:
        op.drop_column("tenants", "signals_agent_config")
        print("✅ Removed signals_agent_config column from tenants table")
    else:
        print("ℹ️  signals_agent_config column does not exist, skipping")
