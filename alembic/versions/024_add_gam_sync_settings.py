"""Add GAM sync settings columns

Revision ID: 024_add_gam_sync_settings
Revises: 023_add_authorized_properties
Create Date: 2025-01-30 12:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "024_add_gam_sync_settings"
down_revision = "023_add_authorized_properties"
branch_labels = None
depends_on = None


def upgrade():
    # Check if columns already exist to make migration idempotent
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Check if adapter_config table exists
    existing_tables = inspector.get_table_names()
    if "adapter_config" not in existing_tables:
        print("⚠️  adapter_config table does not exist, skipping GAM sync settings migration")
        return

    existing_columns = [col["name"] for col in inspector.get_columns("adapter_config")]

    # Add gam_sync_audience_segments column if it doesn't exist
    if "gam_sync_audience_segments" not in existing_columns:
        op.add_column(
            "adapter_config",
            sa.Column("gam_sync_audience_segments", sa.Boolean(), server_default=sa.text("TRUE"), nullable=True)
        )
        print("✅ Added gam_sync_audience_segments column")
    else:
        print("ℹ️  gam_sync_audience_segments column already exists, skipping")

    # Add gam_sync_custom_targeting column if it doesn't exist
    if "gam_sync_custom_targeting" not in existing_columns:
        op.add_column(
            "adapter_config",
            sa.Column("gam_sync_custom_targeting", sa.Boolean(), server_default=sa.text("TRUE"), nullable=True)
        )
        print("✅ Added gam_sync_custom_targeting column")
    else:
        print("ℹ️  gam_sync_custom_targeting column already exists, skipping")


def downgrade():
    # Check if columns exist before dropping to make downgrade idempotent
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Check if adapter_config table exists
    existing_tables = inspector.get_table_names()
    if "adapter_config" not in existing_tables:
        print("⚠️  adapter_config table does not exist, skipping GAM sync settings downgrade")
        return

    existing_columns = [col["name"] for col in inspector.get_columns("adapter_config")]

    # Drop gam_sync_custom_targeting column if it exists
    if "gam_sync_custom_targeting" in existing_columns:
        op.drop_column("adapter_config", "gam_sync_custom_targeting")
        print("✅ Dropped gam_sync_custom_targeting column")

    # Drop gam_sync_audience_segments column if it exists
    if "gam_sync_audience_segments" in existing_columns:
        op.drop_column("adapter_config", "gam_sync_audience_segments")
        print("✅ Dropped gam_sync_audience_segments column")