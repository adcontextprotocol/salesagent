"""Add remaining config fields to database

Revision ID: 006_add_remaining_config_fields
Revises: 005_move_config_to_columns
Create Date: 2025-02-04

"""

from alembic import op
import sqlalchemy as sa
import json


# revision identifiers, used by Alembic.
revision = "006_add_remaining_config_fields"
down_revision = "005_move_config_to_columns"
branch_labels = None
depends_on = None


def upgrade():
    """Add remaining fields from config JSON to proper database columns."""

    # Get the current connection to check column existence
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    existing_columns = [col["name"] for col in inspector.get_columns("tenants")]

    # Add remaining columns to tenants table
    if "slack_audit_webhook_url" not in existing_columns:
        op.add_column("tenants", sa.Column("slack_audit_webhook_url", sa.String(500), nullable=True))
    if "hitl_webhook_url" not in existing_columns:
        op.add_column("tenants", sa.Column("hitl_webhook_url", sa.String(500), nullable=True))
    if "policy_settings" not in existing_columns:
        op.add_column("tenants", sa.Column("policy_settings", sa.Text(), nullable=True))  # JSON

    # Migrate existing data from config JSON
    connection = op.get_bind()

    # Get all tenants with their config
    tenants_table = sa.table(
        "tenants",
        sa.column("tenant_id", sa.String),
        sa.column("config", sa.Text),
        sa.column("slack_audit_webhook_url", sa.String),
        sa.column("hitl_webhook_url", sa.String),
        sa.column("policy_settings", sa.Text),
    )

    tenants = connection.execute(sa.select(tenants_table.c.tenant_id, tenants_table.c.config))

    for tenant in tenants:
        tenant_id = tenant[0]
        config = tenant[1]

        # Parse config JSON
        if isinstance(config, str):
            config = json.loads(config)

        update_data = {}

        # Extract Slack audit webhook
        if "features" in config:
            if "slack_audit_webhook_url" in config["features"]:
                update_data["slack_audit_webhook_url"] = config["features"]["slack_audit_webhook_url"]
            if "hitl_webhook_url" in config["features"]:
                update_data["hitl_webhook_url"] = config["features"]["hitl_webhook_url"]

        # Extract policy settings
        if "policy_settings" in config:
            update_data["policy_settings"] = json.dumps(config["policy_settings"])

        # Update tenant if we have data to update
        if update_data:
            connection.execute(
                tenants_table.update().where(tenants_table.c.tenant_id == tenant_id).values(**update_data)
            )


def downgrade():
    """Restore fields to config JSON."""

    # First reconstruct config JSON from columns
    connection = op.get_bind()

    # Get all tenants with their new column data
    tenants_table = sa.table(
        "tenants",
        sa.column("tenant_id", sa.String),
        sa.column("config", sa.Text),
        sa.column("slack_audit_webhook_url", sa.String),
        sa.column("hitl_webhook_url", sa.String),
        sa.column("policy_settings", sa.Text),
    )

    tenants = connection.execute(
        sa.select(
            tenants_table.c.tenant_id,
            tenants_table.c.config,
            tenants_table.c.slack_audit_webhook_url,
            tenants_table.c.hitl_webhook_url,
            tenants_table.c.policy_settings,
        )
    )

    for row in tenants:
        tenant_id = row[0]
        config = row[1]

        # Parse existing config
        if isinstance(config, str):
            config = json.loads(config)

        # Add fields back to config
        if "features" not in config:
            config["features"] = {}

        if row[2]:  # slack_audit_webhook_url
            config["features"]["slack_audit_webhook_url"] = row[2]
        if row[3]:  # hitl_webhook_url
            config["features"]["hitl_webhook_url"] = row[3]
        if row[4]:  # policy_settings
            config["policy_settings"] = json.loads(row[4])

        # Update config
        connection.execute(
            tenants_table.update().where(tenants_table.c.tenant_id == tenant_id).values(config=json.dumps(config))
        )

    # Drop columns
    op.drop_column("tenants", "policy_settings")
    op.drop_column("tenants", "hitl_webhook_url")
    op.drop_column("tenants", "slack_audit_webhook_url")
