"""Rename enable_aee_signals to enable_axe_signals

Revision ID: 8f8c9aec1458
Revises: 022_add_signals_agent_config
Create Date: 2025-09-07 16:31:10.903399

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8f8c9aec1458"
down_revision: str | Sequence[str] | None = "022_add_signals_agent_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename enable_aee_signals column to enable_axe_signals."""
    # For PostgreSQL, use ALTER TABLE directly
    # For SQLite, batch_alter_table handles the complex rename
    conn = op.get_bind()

    if conn.dialect.name == "postgresql":
        # PostgreSQL rename column syntax
        op.execute("ALTER TABLE tenants RENAME COLUMN enable_aee_signals TO enable_axe_signals")
    else:
        # SQLite requires batch operations
        with op.batch_alter_table("tenants", schema=None) as batch_op:
            batch_op.alter_column("enable_aee_signals", new_column_name="enable_axe_signals")


def downgrade() -> None:
    """Rename enable_axe_signals column back to enable_aee_signals."""
    # For PostgreSQL, use ALTER TABLE directly
    # For SQLite, batch_alter_table handles the complex rename
    conn = op.get_bind()

    if conn.dialect.name == "postgresql":
        # PostgreSQL rename column syntax
        op.execute("ALTER TABLE tenants RENAME COLUMN enable_axe_signals TO enable_aee_signals")
    else:
        # SQLite requires batch operations
        with op.batch_alter_table("tenants", schema=None) as batch_op:
            batch_op.alter_column("enable_axe_signals", new_column_name="enable_aee_signals")
