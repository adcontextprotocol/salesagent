"""Add signals_agents table for multi-agent signals discovery

Revision ID: 024_add_signals_agents
Revises: e17d03b0a79e, 6d6ac8d87c34, ed7d05fea3be, faaed3b71428
Create Date: 2025-10-22 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "024_add_signals_agents"
down_revision: str | Sequence[str] | None = ("e17d03b0a79e", "6d6ac8d87c34", "ed7d05fea3be", "faaed3b71428")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create signals_agents table
    op.create_table(
        "signals_agents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("agent_url", sa.String(length=500), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("auth_type", sa.String(length=50), nullable=True),
        sa.Column("auth_credentials", sa.Text(), nullable=True),
        sa.Column("forward_promoted_offering", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("fallback_to_database", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("timeout", sa.Integer(), nullable=False, server_default=sa.text("30")),
        sa.Column("max_signal_products", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index("idx_signals_agents_tenant", "signals_agents", ["tenant_id"])
    op.create_index("idx_signals_agents_enabled", "signals_agents", ["enabled"])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index("idx_signals_agents_enabled", table_name="signals_agents")
    op.drop_index("idx_signals_agents_tenant", table_name="signals_agents")

    # Drop table
    op.drop_table("signals_agents")
