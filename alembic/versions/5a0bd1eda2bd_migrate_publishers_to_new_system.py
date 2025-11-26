"""migrate_publishers_to_new_system

Migrate existing publisher domains from AuthorizedProperty table to PublisherPartner table.
This enables the new Publishers & Properties UI while preserving existing data.

Revision ID: 5a0bd1eda2bd
Revises: e4f26160e57b
Create Date: 2025-11-25 10:43:47.760976

"""

from typing import Sequence, Union
from datetime import datetime, UTC

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "5a0bd1eda2bd"
down_revision: Union[str, Sequence[str], None] = "e4f26160e57b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Migrate publishers from AuthorizedProperty to PublisherPartner.

    For each tenant:
    1. Find unique publisher_domain values in authorized_properties
    2. Create PublisherPartner records if they don't exist
    3. Mark as verified since properties already exist
    """
    conn = op.get_bind()

    # Find all unique (tenant_id, publisher_domain) combinations
    result = conn.execute(
        text(
            """
        SELECT DISTINCT tenant_id, publisher_domain
        FROM authorized_properties
        WHERE publisher_domain IS NOT NULL
        ORDER BY tenant_id, publisher_domain
    """
        )
    )

    publishers = result.fetchall()

    if not publishers:
        print("No publishers to migrate")
        return

    print(f"Found {len(publishers)} unique publisher domains to migrate")

    # For each publisher, create PublisherPartner if it doesn't exist
    migrated = 0
    skipped = 0

    for tenant_id, publisher_domain in publishers:
        # Check if already exists
        existing = conn.execute(
            text(
                """
            SELECT id FROM publisher_partners
            WHERE tenant_id = :tenant_id AND publisher_domain = :publisher_domain
        """
            ),
            {"tenant_id": tenant_id, "publisher_domain": publisher_domain},
        ).fetchone()

        if existing:
            skipped += 1
            continue

        # Create new PublisherPartner record
        now = datetime.now(UTC)
        conn.execute(
            text(
                """
            INSERT INTO publisher_partners
                (tenant_id, publisher_domain, display_name, is_verified, sync_status, created_at, updated_at)
            VALUES
                (:tenant_id, :publisher_domain, :display_name, :is_verified, :sync_status, :created_at, :updated_at)
        """
            ),
            {
                "tenant_id": tenant_id,
                "publisher_domain": publisher_domain,
                "display_name": publisher_domain,  # Use domain as display name
                "is_verified": False,  # Not verified - users must click "Sync All Publishers" to verify
                "sync_status": "pending",  # Pending verification
                "created_at": now,
                "updated_at": now,
            },
        )

        migrated += 1

    print(f"Migration complete: {migrated} publishers migrated, {skipped} already existed")


def downgrade() -> None:
    """Remove migrated PublisherPartner records.

    Note: This only removes PublisherPartner records that match domains in AuthorizedProperty.
    It does NOT delete AuthorizedProperty data.
    """
    conn = op.get_bind()

    # Delete PublisherPartner records that have matching authorized_properties
    result = conn.execute(
        text(
            """
        DELETE FROM publisher_partners
        WHERE (tenant_id, publisher_domain) IN (
            SELECT DISTINCT tenant_id, publisher_domain
            FROM authorized_properties
            WHERE publisher_domain IS NOT NULL
        )
    """
        )
    )

    print(f"Downgrade complete: Removed {result.rowcount} PublisherPartner records")
