"""add_buyer_ref_unique_constraint_and_update_template

Revision ID: 31ff6218695a
Revises: 9309ac2fa74f
Create Date: 2025-10-12 20:31:23.864667

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "31ff6218695a"
down_revision: str | Sequence[str] | None = "9309ac2fa74f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # First, fix any duplicate buyer_ref values by appending a sequence number
    # This handles the case where test data has duplicate buyer_refs
    op.execute(
        """
        WITH duplicates AS (
            SELECT
                media_buy_id,
                tenant_id,
                principal_id,
                buyer_ref,
                ROW_NUMBER() OVER (
                    PARTITION BY tenant_id, principal_id, buyer_ref
                    ORDER BY created_at
                ) as rn
            FROM media_buys
            WHERE buyer_ref IS NOT NULL
        )
        UPDATE media_buys
        SET buyer_ref = duplicates.buyer_ref || '-' || duplicates.rn
        FROM duplicates
        WHERE media_buys.media_buy_id = duplicates.media_buy_id
          AND duplicates.rn > 1
        """
    )

    # Now add unique constraint on (tenant_id, principal_id, buyer_ref)
    # Note: This only constrains non-NULL buyer_ref values (PostgreSQL behavior)
    op.create_unique_constraint("uq_media_buys_buyer_ref", "media_buys", ["tenant_id", "principal_id", "buyer_ref"])

    # Update default order name template to include buyer_ref
    op.execute(
        """
        UPDATE tenants
        SET order_name_template = '{campaign_name|promoted_offering} - {buyer_ref} - {date_range}'
        WHERE order_name_template = '{campaign_name|promoted_offering} - {date_range}'
           OR order_name_template IS NULL
    """
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Remove unique constraint
    op.drop_constraint("uq_media_buys_buyer_ref", "media_buys", type_="unique")

    # Revert order name template to old default (only for tenants still using the new default)
    op.execute(
        """
        UPDATE tenants
        SET order_name_template = '{campaign_name|promoted_offering} - {date_range}'
        WHERE order_name_template = '{campaign_name|promoted_offering} - {buyer_ref} - {date_range}'
    """
    )
