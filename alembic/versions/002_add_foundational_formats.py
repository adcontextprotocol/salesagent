"""Add foundational format support

Revision ID: 002
Revises: initial_schema
Create Date: 2025-01-31

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    """Add extends and is_foundational fields to creative_formats table."""

    # Add new columns
    op.add_column("creative_formats", sa.Column("extends", sa.String(50), nullable=True))
    op.add_column("creative_formats", sa.Column("is_foundational", sa.Boolean(), nullable=False, server_default="0"))
    op.add_column("creative_formats", sa.Column("modifications", sa.Text(), nullable=True))

    # Create index for foundational formats
    op.create_index("idx_creative_formats_foundational", "creative_formats", ["is_foundational"])
    op.create_index("idx_creative_formats_extends", "creative_formats", ["extends"])

    # Skip foreign key constraint for SQLite - it's handled at table creation
    # PostgreSQL will support this, but SQLite requires batch mode
    # The constraint is already defined in the model


def downgrade():
    """Remove foundational format support."""

    # Drop indexes
    op.drop_index("idx_creative_formats_extends", "creative_formats")
    op.drop_index("idx_creative_formats_foundational", "creative_formats")

    # Drop columns
    op.drop_column("creative_formats", "modifications")
    op.drop_column("creative_formats", "is_foundational")
    op.drop_column("creative_formats", "extends")
