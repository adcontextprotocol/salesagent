"""add_webhook_delivery_log

Revision ID: 1759f70fc76a
Revises: fa617dd8b051
Create Date: 2025-11-13 11:04:24.614512

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1759f70fc76a"
down_revision: Union[str, Sequence[str], None] = ("fa617dd8b051", "039d59477ab4")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "webhook_delivery_log",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("principal_id", sa.String(), nullable=False),
        sa.Column("media_buy_id", sa.String(), nullable=False),
        sa.Column("webhook_url", sa.String(), nullable=False),
        sa.Column("task_type", sa.String(), nullable=False),  # "delivery_report"
        sa.Column("sequence_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("notification_type", sa.String(), nullable=True),  # "scheduled", "final", "delayed", "adjusted"
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(), nullable=False),  # "success", "failed", "retrying"
        sa.Column("http_status_code", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("payload_size_bytes", sa.Integer(), nullable=True),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Indexes for common queries
    op.create_index("idx_webhook_log_media_buy", "webhook_delivery_log", ["media_buy_id"])
    op.create_index("idx_webhook_log_tenant", "webhook_delivery_log", ["tenant_id"])
    op.create_index("idx_webhook_log_status", "webhook_delivery_log", ["status"])
    op.create_index("idx_webhook_log_created_at", "webhook_delivery_log", ["created_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_webhook_log_created_at", table_name="webhook_delivery_log")
    op.drop_index("idx_webhook_log_status", table_name="webhook_delivery_log")
    op.drop_index("idx_webhook_log_tenant", table_name="webhook_delivery_log")
    op.drop_index("idx_webhook_log_media_buy", table_name="webhook_delivery_log")
    op.drop_table("webhook_delivery_log")
