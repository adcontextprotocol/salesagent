"""Remove tenant-level advertiser_id and move to principal platform_mappings

Revision ID: 013_principal_advertiser_mapping
Revises: 012_add_gam_orders_line_items
Create Date: 2025-01-09

"""

import json

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic
revision = "013_principal_advertiser_mapping"
down_revision = "012_add_gam_orders_line_items"
branch_labels = None
depends_on = None


def upgrade():
    """
    Migration to move advertiser_id from tenant-level to principal-level.
    The gam_company_id column in adapter_config will be removed since each
    principal will have their own advertiser mapping.

    Note: We're not actually removing the column yet to avoid breaking existing deployments.
    The column will be ignored in the code and can be removed in a future migration.
    """

    # Get connection for data migration
    connection = op.get_bind()

    # Migrate existing data: copy company_id to all principals' platform_mappings
    # First, get all tenants with GAM configured
    result = connection.execute(
        sa.text(
            """
        SELECT tenant_id, gam_company_id
        FROM adapter_config
        WHERE adapter_type = 'google_ad_manager' AND gam_company_id IS NOT NULL
    """
        )
    )

    for row in result:
        tenant_id = row[0]
        company_id = row[1]

        # Update all principals for this tenant to include the advertiser_id
        principals_result = connection.execute(
            sa.text("SELECT principal_id, platform_mappings FROM principals WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        )

        for principal_row in principals_result:
            principal_id = principal_row[0]
            try:
                platform_mappings = json.loads(principal_row[1]) if principal_row[1] else {}
                if not isinstance(platform_mappings, dict):
                    platform_mappings = {}
            except (json.JSONDecodeError, TypeError):
                platform_mappings = {}
                print(f"Warning: Invalid platform_mappings for principal {principal_id}, using empty dict")

            # Add the advertiser_id to platform_mappings using new format
            # Check both old and new formats to avoid duplicates
            has_gam_mapping = "gam_advertiser_id" in platform_mappings or (
                "google_ad_manager" in platform_mappings and platform_mappings["google_ad_manager"].get("advertiser_id")
            )

            if not has_gam_mapping:
                # Use new format
                if "google_ad_manager" not in platform_mappings:
                    platform_mappings["google_ad_manager"] = {}
                platform_mappings["google_ad_manager"]["advertiser_id"] = str(company_id)
                platform_mappings["google_ad_manager"]["enabled"] = True

                connection.execute(
                    sa.text(
                        """
                        UPDATE principals
                        SET platform_mappings = :mappings
                        WHERE tenant_id = :tenant_id AND principal_id = :principal_id
                    """
                    ),
                    {"mappings": json.dumps(platform_mappings), "tenant_id": tenant_id, "principal_id": principal_id},
                )

    # Note: We're keeping gam_company_id column for now to avoid breaking existing deployments
    # It will be ignored in the code and can be removed in a future migration


def downgrade():
    """
    Revert the migration by copying the first principal's advertiser_id back to tenant level.
    """
    connection = op.get_bind()

    # For each tenant, take the first principal's advertiser_id and copy it back to adapter_config
    result = connection.execute(
        sa.text(
            """
        SELECT DISTINCT p.tenant_id, p.platform_mappings
        FROM principals p
        JOIN adapter_config a ON p.tenant_id = a.tenant_id
        WHERE a.adapter_type = 'google_ad_manager'
    """
        )
    )

    for row in result:
        tenant_id = row[0]
        try:
            platform_mappings = json.loads(row[1]) if row[1] else {}
            if not isinstance(platform_mappings, dict):
                platform_mappings = {}
        except (json.JSONDecodeError, TypeError):
            platform_mappings = {}
            print(f"Warning: Invalid platform_mappings for tenant {tenant_id}, using empty dict")

        # Support both old and new formats
        advertiser_id = platform_mappings.get("gam_advertiser_id")
        if not advertiser_id and "google_ad_manager" in platform_mappings:
            advertiser_id = platform_mappings["google_ad_manager"].get("advertiser_id")

        if advertiser_id:
            connection.execute(
                sa.text(
                    """
                    UPDATE adapter_config
                    SET gam_company_id = :advertiser_id
                    WHERE tenant_id = :tenant_id
                """
                ),
                {"advertiser_id": advertiser_id, "tenant_id": tenant_id},
            )
