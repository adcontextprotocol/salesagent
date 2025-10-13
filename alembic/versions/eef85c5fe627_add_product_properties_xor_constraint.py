"""add_product_properties_xor_constraint

Revision ID: eef85c5fe627
Revises: 00b3c68c3ac6
Create Date: 2025-10-13 10:08:11.158300

This migration adds a database-level CheckConstraint to enforce the AdCP v2.4
oneOf requirement: products MUST have EITHER properties OR property_tags (not both, not neither).

This complements the Pydantic schema validation and prevents invalid data at the database layer.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eef85c5fe627'
down_revision: Union[str, Sequence[str], None] = '00b3c68c3ac6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add CheckConstraint for XOR(properties, property_tags)."""
    op.create_check_constraint(
        "ck_product_properties_xor",
        "products",
        "(properties IS NOT NULL AND property_tags IS NULL) OR (properties IS NULL AND property_tags IS NOT NULL)",
    )
    print("✅ Added database-level XOR constraint for product property authorization")


def downgrade() -> None:
    """Remove CheckConstraint."""
    op.drop_constraint("ck_product_properties_xor", "products", type_="check")
