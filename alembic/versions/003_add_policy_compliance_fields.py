"""Add audience characteristic fields to products table

Revision ID: 003_add_policy_compliance_fields
Revises: 002
Create Date: 2025-08-03

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "003_add_policy_compliance_fields"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade():
    """Add audience characteristic fields to products table."""

    # Add new columns for simplified audience characteristics
    op.add_column("products", sa.Column("targeted_ages", sa.Text(), nullable=True))
    op.add_column("products", sa.Column("verified_minimum_age", sa.Integer(), nullable=True))

    # Create index for verified minimum age field for faster filtering
    op.create_index("idx_products_verified_min_age", "products", ["verified_minimum_age"])


def downgrade():
    """Remove audience characteristic fields from products table."""

    # Drop index
    op.drop_index("idx_products_verified_min_age", "products")

    # Drop columns
    op.drop_column("products", "verified_minimum_age")
    op.drop_column("products", "targeted_ages")
