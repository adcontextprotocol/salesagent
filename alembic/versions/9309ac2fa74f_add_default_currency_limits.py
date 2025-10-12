"""add_default_currency_limits

Revision ID: 9309ac2fa74f
Revises: 62bc22421983
Create Date: 2025-10-12 07:58:35.542405

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9309ac2fa74f"
down_revision: str | Sequence[str] | None = "62bc22421983"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add default currency limits (USD, EUR, GBP) to all existing tenants.

    This migration ensures that all tenants support the most common currencies
    with no minimum budget requirement and a generous daily maximum.

    **Context**: The currency_limits table was introduced earlier but existing
    tenants were not seeded with default data, causing all create_media_buy
    requests to fail with "Currency X is not supported by this publisher".
    """
    # Get connection
    conn = op.get_bind()

    # Get all tenant IDs
    result = conn.execute(sa.text("SELECT tenant_id FROM tenants"))
    tenant_ids = [row[0] for row in result]

    # Add USD, EUR, GBP for each tenant with:
    # - min_package_budget = 0 (no minimum)
    # - max_daily_package_spend = 100000 (generous limit)
    for tenant_id in tenant_ids:
        for currency in ["USD", "EUR", "GBP"]:
            conn.execute(
                sa.text(
                    """
                INSERT INTO currency_limits
                (tenant_id, currency_code, min_package_budget, max_daily_package_spend, created_at, updated_at)
                VALUES (:tenant_id, :currency, 0.00, 100000.00, NOW(), NOW())
                ON CONFLICT (tenant_id, currency_code) DO NOTHING
            """
                ),
                {"tenant_id": tenant_id, "currency": currency},
            )

    print(f"✅ Added default currency limits (USD, EUR, GBP) to {len(tenant_ids)} tenants")


def downgrade() -> None:
    """Remove default currency limits added by this migration.

    Note: This only removes limits with the exact default values.
    Custom limits are preserved.
    """
    conn = op.get_bind()

    # Remove only the default limits (min=0, max_daily=100000)
    conn.execute(
        sa.text(
            """
        DELETE FROM currency_limits
        WHERE currency_code IN ('USD', 'EUR', 'GBP')
          AND min_package_budget = 0.00
          AND max_daily_package_spend = 100000.00
    """
        )
    )

    print("✅ Removed default currency limits")
