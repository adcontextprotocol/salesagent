"""Add platform_config to creative_formats

Revision ID: 018_platform_config
Revises: 017_handle_partial_schemas
Create Date: 2025-10-07 12:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers
revision = "018_platform_config"
down_revision = "017_handle_partial_schemas"
branch_labels = None
depends_on = None


def upgrade():
    """Add platform_config column to creative_formats table.

    This column stores platform-specific configuration like GAM creative template IDs,
    allowing formats to specify custom creative placeholder settings per ad server.
    """
    # Check if we're using PostgreSQL or SQLite
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        # PostgreSQL: Use JSONB for better performance
        op.add_column(
            "creative_formats",
            sa.Column("platform_config", postgresql.JSONB(), nullable=True),
        )
    else:
        # SQLite: Use TEXT for JSON
        op.add_column(
            "creative_formats",
            sa.Column("platform_config", sa.Text(), nullable=True),
        )


def downgrade():
    """Remove platform_config column."""
    op.drop_column("creative_formats", "platform_config")
