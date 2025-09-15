"""Fix inventory_type column length

Revision ID: 009_fix_inventory_type_length
Revises: 008_add_gam_inventory_tables
Create Date: 2025-08-05

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "009_fix_inventory_type_length"
down_revision = "008_add_gam_inventory_tables"
branch_labels = None
depends_on = None


def upgrade():
    # Increase inventory_type column length from 20 to 30 to accommodate 'custom_targeting_value'
    with op.batch_alter_table("gam_inventory") as batch_op:
        batch_op.alter_column(
            "inventory_type", existing_type=sa.String(length=20), type_=sa.String(length=30), existing_nullable=False
        )

    with op.batch_alter_table("product_inventory_mappings") as batch_op:
        batch_op.alter_column(
            "inventory_type", existing_type=sa.String(length=20), type_=sa.String(length=30), existing_nullable=False
        )


def downgrade():
    # Revert column length back to 20
    with op.batch_alter_table("product_inventory_mappings") as batch_op:
        batch_op.alter_column(
            "inventory_type", existing_type=sa.String(length=30), type_=sa.String(length=20), existing_nullable=False
        )

    with op.batch_alter_table("gam_inventory") as batch_op:
        batch_op.alter_column(
            "inventory_type", existing_type=sa.String(length=30), type_=sa.String(length=20), existing_nullable=False
        )
