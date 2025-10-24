"""Add signals-backed products and dynamic product mappings

Revision ID: fa5cffb9582b
Revises: 024_add_signals_agents
Create Date: 2025-10-23 21:36:00.286419

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fa5cffb9582b"
down_revision: str | Sequence[str] | None = "024_add_signals_agents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add signals-backed product columns to products table
    op.add_column("products", sa.Column("is_signals_backed", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("products", sa.Column("signals_config", sa.JSON(), nullable=True))

    # Create dynamic_product_mappings table
    op.create_table(
        "dynamic_product_mappings",
        sa.Column("product_id", sa.String(100), primary_key=True),
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("template_product_id", sa.String(100), nullable=False),
        sa.Column("signal_agent_id", sa.Integer(), nullable=False),
        sa.Column("signal_id", sa.String(200), nullable=False),
        sa.Column("signal_data", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "template_product_id"], ["products.tenant_id", "products.product_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["signal_agent_id"], ["signals_agents.id"]),
    )
    op.create_index("idx_dynamic_products_tenant", "dynamic_product_mappings", ["tenant_id"])
    op.create_index("idx_dynamic_products_expires", "dynamic_product_mappings", ["expires_at"])
    op.create_index("idx_dynamic_products_signal", "dynamic_product_mappings", ["signal_agent_id", "signal_id"])

    # Create signal_activations table
    op.create_table(
        "signal_activations",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("media_buy_id", sa.String(100), nullable=False),
        sa.Column("signal_agent_id", sa.Integer(), nullable=False),
        sa.Column("signal_id", sa.String(200), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("activation_task_id", sa.String(200), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("has_push_notification", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("webhook_received", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("last_webhook_at", sa.DateTime(), nullable=True),
        sa.Column("last_polled_at", sa.DateTime(), nullable=True),
        sa.Column("next_poll_at", sa.DateTime(), nullable=True),
        sa.Column("poll_interval_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("poll_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_poll_attempts", sa.Integer(), nullable=False, server_default="288"),
        sa.Column("gam_segment_id", sa.String(200), nullable=True),
        sa.Column("gam_key_values", sa.JSON(), nullable=True),
        sa.Column("activation_metadata", sa.JSON(), nullable=True),
        sa.Column("activation_error", sa.Text(), nullable=True),
        sa.Column("estimated_completion_time", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("activated_at", sa.DateTime(), nullable=True),
        sa.Column("failed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["media_buy_id"], ["media_buys.media_buy_id"]),
        sa.ForeignKeyConstraint(["signal_agent_id"], ["signals_agents.id"]),
    )
    op.create_index("idx_signal_activations_media_buy", "signal_activations", ["media_buy_id"])
    op.create_index("idx_signal_activations_status", "signal_activations", ["status"])
    op.create_index("idx_signal_activations_next_poll", "signal_activations", ["next_poll_at"])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop tables
    op.drop_table("signal_activations")
    op.drop_table("dynamic_product_mappings")

    # Drop product columns
    op.drop_column("products", "signals_config")
    op.drop_column("products", "is_signals_backed")
