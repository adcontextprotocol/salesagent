"""Add missing updated_at column to creative_formats

Revision ID: 018_add_missing_updated_at
Revises: 017_handle_partial_schemas
Create Date: 2025-08-18

"""

import sqlalchemy as sa
from sqlalchemy.sql import func

from alembic import op

# revision identifiers, used by Alembic.
revision = "018_add_missing_updated_at"
down_revision = "017_handle_partial_schemas"
branch_labels = None
depends_on = None


def upgrade():
    """Add updated_at column to creative_formats table if it doesn't exist."""
    # Check if column exists (for PostgreSQL and SQLite compatibility)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("creative_formats")]

    if "updated_at" not in columns:
        op.add_column(
            "creative_formats", sa.Column("updated_at", sa.DateTime(), server_default=func.now(), nullable=True)
        )


def downgrade():
    """Remove updated_at column from creative_formats table."""
    op.drop_column("creative_formats", "updated_at")
