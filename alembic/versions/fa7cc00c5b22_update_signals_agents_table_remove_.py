"""Update signals_agents table - remove priority, max_signal_products, fallback_to_database, add auth_header

Revision ID: fa7cc00c5b22
Revises: 28a56a4aaa17
Create Date: 2025-10-25 20:53:43.893212

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fa7cc00c5b22"
down_revision: str | Sequence[str] | None = "28a56a4aaa17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add auth_header column
    op.add_column("signals_agents", sa.Column("auth_header", sa.String(length=100), nullable=True))

    # Remove columns that are now per-product settings
    op.drop_column("signals_agents", "priority")
    op.drop_column("signals_agents", "max_signal_products")
    op.drop_column("signals_agents", "fallback_to_database")


def downgrade() -> None:
    """Downgrade schema."""
    # Add back removed columns
    op.add_column(
        "signals_agents",
        sa.Column("fallback_to_database", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "signals_agents", sa.Column("max_signal_products", sa.Integer(), nullable=False, server_default=sa.text("10"))
    )
    op.add_column("signals_agents", sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("10")))

    # Remove auth_header column
    op.drop_column("signals_agents", "auth_header")
