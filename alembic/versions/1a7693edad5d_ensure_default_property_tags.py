"""ensure_default_property_tags

Ensures all tenants have a default 'all_inventory' PropertyTag.
This tag is commonly used in products to indicate coverage of all properties.

Revision ID: 1a7693edad5d
Revises: 0d4fe6eb03ab
Create Date: 2025-10-16 16:43:51.255012

"""

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1a7693edad5d"
down_revision: str | Sequence[str] | None = "0d4fe6eb03ab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Ensure all tenants have default property tags."""
    conn = op.get_bind()

    # Get all tenants
    result = conn.execute(text("SELECT tenant_id FROM tenants"))
    tenant_ids = [row[0] for row in result]

    # For each tenant, ensure 'all_inventory' property tag exists
    for tenant_id in tenant_ids:
        # Check if tag already exists
        existing = conn.execute(
            text("SELECT COUNT(*) FROM property_tags WHERE tenant_id = :tenant_id AND tag_id = 'all_inventory'"),
            {"tenant_id": tenant_id},
        ).scalar()

        if not existing:
            # Insert the default tag
            conn.execute(
                text(
                    """
                    INSERT INTO property_tags (tenant_id, tag_id, name, description, created_at, updated_at)
                    VALUES (:tenant_id, 'all_inventory', 'All Inventory',
                            'All available inventory across all properties', NOW(), NOW())
                """
                ),
                {"tenant_id": tenant_id},
            )
            print(f"✅ Created 'all_inventory' PropertyTag for tenant {tenant_id}")
        else:
            print(f"ℹ️  'all_inventory' PropertyTag already exists for tenant {tenant_id}")


def downgrade() -> None:
    """Remove default property tags created by this migration."""
    conn = op.get_bind()

    # Remove all 'all_inventory' tags that were created by this migration
    # Note: We only remove tags with the exact description we created
    conn.execute(
        text(
            """
            DELETE FROM property_tags
            WHERE tag_id = 'all_inventory'
            AND description = 'All available inventory across all properties'
        """
        )
    )
    print("Removed default 'all_inventory' PropertyTags")
