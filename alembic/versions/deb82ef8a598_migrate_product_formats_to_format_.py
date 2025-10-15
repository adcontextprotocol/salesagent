"""migrate_product_formats_to_format_references

Migrates Product.formats from list[str] to list[FormatReference].

This migration converts existing product formats from simple string IDs like:
    ["display_300x250", "video_1280x720"]

To FormatReference objects with agent_url:
    [
        {"agent_url": "https://creative.adcontextprotocol.org", "format_id": "display_300x250"},
        {"agent_url": "https://creative.adcontextprotocol.org", "format_id": "video_1280x720"}
    ]

All existing formats are migrated to use the default AdCP creative agent.

Revision ID: deb82ef8a598
Revises: 31ff6218695a
Create Date: 2025-10-12 22:04:09.934758

"""

import json
from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "deb82ef8a598"
down_revision: str | Sequence[str] | None = "31ff6218695a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Default creative agent URL
DEFAULT_AGENT_URL = "https://creative.adcontextprotocol.org"


def upgrade() -> None:
    """Migrate product formats to FormatReference objects."""
    conn = op.get_bind()

    # Get all products
    result = conn.execute(text("SELECT tenant_id, product_id, formats FROM products"))
    products = result.fetchall()

    print(f"\n🔄 Migrating {len(products)} products to FormatReference format...")

    migrated_count = 0
    for product in products:
        tenant_id, product_id, formats_json = product

        # Parse existing formats
        if isinstance(formats_json, str):
            formats = json.loads(formats_json)
        else:
            formats = formats_json

        # Skip if already migrated (first item is a dict with agent_url)
        if formats and isinstance(formats[0], dict) and "agent_url" in formats[0]:
            print(f"  ⏭️  Skipping {tenant_id}/{product_id} (already migrated)")
            continue

        # Convert string IDs to FormatReference objects
        new_formats = []
        for format_id in formats:
            if isinstance(format_id, str):
                new_formats.append({"agent_url": DEFAULT_AGENT_URL, "format_id": format_id})
            else:
                # Already a dict, ensure it has agent_url
                if "agent_url" not in format_id:
                    format_id["agent_url"] = DEFAULT_AGENT_URL
                new_formats.append(format_id)

        # Update product with new format structure
        conn.execute(
            text("UPDATE products SET formats = :formats WHERE tenant_id = :tenant_id AND product_id = :product_id"),
            {"formats": json.dumps(new_formats), "tenant_id": tenant_id, "product_id": product_id},
        )

        migrated_count += 1
        print(f"  ✅ Migrated {tenant_id}/{product_id}: {len(new_formats)} formats")

    print(f"\n✅ Migration complete: {migrated_count} products migrated\n")


def downgrade() -> None:
    """Revert FormatReference objects back to simple string IDs."""
    conn = op.get_bind()

    # Get all products
    result = conn.execute(text("SELECT tenant_id, product_id, formats FROM products"))
    products = result.fetchall()

    print(f"\n🔄 Reverting {len(products)} products to string format IDs...")

    reverted_count = 0
    for product in products:
        tenant_id, product_id, formats_json = product

        # Parse existing formats
        if isinstance(formats_json, str):
            formats = json.loads(formats_json)
        else:
            formats = formats_json

        # Skip if already in string format
        if formats and isinstance(formats[0], str):
            print(f"  ⏭️  Skipping {tenant_id}/{product_id} (already in string format)")
            continue

        # Convert FormatReference objects to string IDs
        format_ids = []
        for fmt in formats:
            if isinstance(fmt, dict) and "format_id" in fmt:
                format_ids.append(fmt["format_id"])
            elif isinstance(fmt, str):
                format_ids.append(fmt)

        # Update product with old format structure
        conn.execute(
            text("UPDATE products SET formats = :formats WHERE tenant_id = :tenant_id AND product_id = :product_id"),
            {"formats": json.dumps(format_ids), "tenant_id": tenant_id, "product_id": product_id},
        )

        reverted_count += 1
        print(f"  ✅ Reverted {tenant_id}/{product_id}: {len(format_ids)} formats")

    print(f"\n✅ Revert complete: {reverted_count} products reverted\n")
