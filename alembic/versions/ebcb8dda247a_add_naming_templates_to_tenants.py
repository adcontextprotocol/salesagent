"""add_naming_templates_to_tenants

Revision ID: ebcb8dda247a
Revises: e2d9b45ea2bc
Create Date: 2025-10-08 05:28:03.366004

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ebcb8dda247a"
down_revision: str | Sequence[str] | None = "e2d9b45ea2bc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Default templates
DEFAULT_ORDER_TEMPLATE = "{campaign_name|promoted_offering} - {date_range}"
DEFAULT_LINE_ITEM_TEMPLATE = "{order_name} - {product_name}"


def upgrade() -> None:
    """Add naming template columns to tenants table.

    Consolidates order and line item naming templates from adapter_config
    to tenant level, making them available across all adapters (GAM, Mock, etc.)
    """
    # Step 1: Add naming template columns (nullable, no server_default)
    # Note: server_default only affects new rows, not existing ones
    op.add_column(
        "tenants",
        sa.Column("order_name_template", sa.String(500), nullable=True),
    )
    op.add_column(
        "tenants",
        sa.Column("line_item_name_template", sa.String(500), nullable=True),
    )

    # Step 2: Migrate existing naming templates from adapter_config
    conn = op.get_bind()

    result = conn.execute(
        sa.text(
            """
        SELECT DISTINCT
            ac.tenant_id,
            ac.gam_order_name_template,
            ac.gam_line_item_name_template
        FROM adapter_config ac
        WHERE ac.adapter_type = 'google_ad_manager'
          AND (ac.gam_order_name_template IS NOT NULL
               OR ac.gam_line_item_name_template IS NOT NULL)
    """
        )
    )

    # Update tenants with their existing GAM templates
    for row in result:
        tenant_id = row[0]
        order_template = row[1]
        line_item_template = row[2]

        if order_template or line_item_template:
            update_sql = "UPDATE tenants SET "
            updates = []
            params = {"tenant_id": tenant_id}

            if order_template:
                updates.append("order_name_template = :order_template")
                params["order_template"] = order_template

            if line_item_template:
                updates.append("line_item_name_template = :line_item_template")
                params["line_item_template"] = line_item_template

            update_sql += ", ".join(updates) + " WHERE tenant_id = :tenant_id"
            conn.execute(sa.text(update_sql), params)

    # Step 3: Backfill NULL values with defaults for all tenants
    conn.execute(
        sa.text(
            """
        UPDATE tenants
        SET order_name_template = :default_order
        WHERE order_name_template IS NULL
    """
        ),
        {"default_order": DEFAULT_ORDER_TEMPLATE},
    )

    conn.execute(
        sa.text(
            """
        UPDATE tenants
        SET line_item_name_template = :default_line_item
        WHERE line_item_name_template IS NULL
    """
        ),
        {"default_line_item": DEFAULT_LINE_ITEM_TEMPLATE},
    )

    # NOTE: We're keeping the old columns in adapter_config for backward compatibility
    # They can be removed in a future migration after verifying all code uses tenant columns
    # NOTE: No explicit commit() - Alembic handles transaction management


def downgrade() -> None:
    """Cannot downgrade - would cause data loss.

    This migration moves data from adapter_config to tenants table.
    Downgrading would lose any customizations made after migration.

    To rollback, restore database from backup taken before migration.
    """
    raise RuntimeError(
        "Downgrade not supported for naming template migration. "
        "Templates have been migrated from adapter_config to tenant level. "
        "Automatic restoration is not possible without data loss risk. "
        "\n\n"
        "To rollback this migration:\n"
        "1. Restore database from backup taken before migration\n"
        "2. Run: alembic downgrade e2d9b45ea2bc\n"
        "3. Redeploy previous application version\n"
        "\n"
        "Contact database administrator if you need assistance."
    )
