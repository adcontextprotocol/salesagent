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


def upgrade() -> None:
    """Add naming template columns to tenants table.

    Consolidates order and line item naming templates from adapter_config
    to tenant level, making them available across all adapters (GAM, Mock, etc.)
    """
    # Add naming template columns to tenants table
    op.add_column(
        "tenants",
        sa.Column(
            "order_name_template",
            sa.String(500),
            nullable=True,
            server_default="{campaign_name|promoted_offering} - {date_range}",
        ),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "line_item_name_template",
            sa.String(500),
            nullable=True,
            server_default="{order_name} - {product_name}",
        ),
    )

    # Migrate existing naming templates from adapter_config to tenants
    conn = op.get_bind()

    # Get all tenants with GAM adapter configs that have naming templates
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

    # Update tenants with their existing templates
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

    # Commit the migration transaction
    conn.commit()

    # NOTE: We're keeping the old columns in adapter_config for backward compatibility
    # They can be removed in a future migration after verifying all code uses tenant columns


def downgrade() -> None:
    """Remove naming template columns from tenants table."""
    # Remove columns
    op.drop_column("tenants", "line_item_name_template")
    op.drop_column("tenants", "order_name_template")

    # NOTE: This downgrade does NOT restore data to adapter_config
    # If you need to rollback, you should restore from a backup
