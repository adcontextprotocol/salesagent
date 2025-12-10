"""add_principal_access_to_products

Add allowed_principal_ids field to products table for restricting product
visibility to specific principals/advertisers.

When null or empty array, product is visible to all principals (default).
When populated, only those specific principals can see the product.

Revision ID: a1b2c3d4e5f6
Revises: 661829084198
Create Date: 2025-12-09

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "661829084198"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add allowed_principal_ids column to products table.

    NULL or empty array means visible to all principals (default behavior).
    When populated with principal IDs, only those principals can see the product.
    """
    op.add_column(
        "products",
        sa.Column(
            "allowed_principal_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="List of principal IDs that can see this product. NULL/empty means visible to all.",
        ),
    )

    # Add a GIN index for efficient JSONB array containment queries
    op.create_index(
        "idx_products_allowed_principals",
        "products",
        ["allowed_principal_ids"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Remove allowed_principal_ids column from products table."""
    op.drop_index("idx_products_allowed_principals", table_name="products")
    op.drop_column("products", "allowed_principal_ids")
