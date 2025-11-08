"""add_inventory_profiles_table

Revision ID: 4efe7b2471a9
Revises: d169f2e66919
Create Date: 2025-11-08 05:28:50.943046

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4efe7b2471a9"
down_revision: str | Sequence[str] | None = "d169f2e66919"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create inventory_profiles table
    op.create_table(
        "inventory_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("profile_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("inventory_config", sa.JSON(), nullable=False),
        sa.Column("formats", sa.JSON(), nullable=False),
        sa.Column("publisher_properties", sa.JSON(), nullable=False),
        sa.Column("targeting_template", sa.JSON(), nullable=True),
        sa.Column("gam_preset_id", sa.String(length=100), nullable=True),
        sa.Column("gam_preset_sync_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "profile_id", name="uq_inventory_profile"),
    )
    op.create_index("idx_inventory_profiles_tenant", "inventory_profiles", ["tenant_id"])

    # Add inventory_profile_id column to products table
    op.add_column("products", sa.Column("inventory_profile_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_products_inventory_profile",
        "products",
        "inventory_profiles",
        ["inventory_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_products_inventory_profile", "products", ["inventory_profile_id"])


def downgrade() -> None:
    """Downgrade schema."""
    # Remove foreign key and column from products
    op.drop_index("idx_products_inventory_profile", table_name="products")
    op.drop_constraint("fk_products_inventory_profile", "products", type_="foreignkey")
    op.drop_column("products", "inventory_profile_id")

    # Drop inventory_profiles table
    op.drop_index("idx_inventory_profiles_tenant", table_name="inventory_profiles")
    op.drop_table("inventory_profiles")
