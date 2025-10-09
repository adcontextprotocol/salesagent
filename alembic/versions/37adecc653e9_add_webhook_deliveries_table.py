"""add_webhook_deliveries_table

Revision ID: 37adecc653e9
Revises: 6c2d562e3ee4
Create Date: 2025-10-08 22:06:14.468131

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "37adecc653e9"
down_revision: str | Sequence[str] | None = "6c2d562e3ee4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create webhook_deliveries table for tracking webhook delivery attempts."""
    # Import JSONType for JSONB handling
    from src.core.database.json_type import JSONType

    op.create_table(
        "webhook_deliveries",
        sa.Column("delivery_id", sa.String(100), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(50), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
        sa.Column("webhook_url", sa.String(500), nullable=False),
        sa.Column("payload", JSONType, nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("object_id", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime, nullable=True),
        sa.Column("delivered_at", sa.DateTime, nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("response_code", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # Create indexes
    op.create_index("idx_webhook_deliveries_tenant", "webhook_deliveries", ["tenant_id"])
    op.create_index("idx_webhook_deliveries_status", "webhook_deliveries", ["status"])
    op.create_index("idx_webhook_deliveries_event_type", "webhook_deliveries", ["event_type"])
    op.create_index("idx_webhook_deliveries_object_id", "webhook_deliveries", ["object_id"])
    op.create_index("idx_webhook_deliveries_created", "webhook_deliveries", ["created_at"])


def downgrade() -> None:
    """Drop webhook_deliveries table."""
    op.drop_index("idx_webhook_deliveries_created", "webhook_deliveries")
    op.drop_index("idx_webhook_deliveries_object_id", "webhook_deliveries")
    op.drop_index("idx_webhook_deliveries_event_type", "webhook_deliveries")
    op.drop_index("idx_webhook_deliveries_status", "webhook_deliveries")
    op.drop_index("idx_webhook_deliveries_tenant", "webhook_deliveries")
    op.drop_table("webhook_deliveries")
