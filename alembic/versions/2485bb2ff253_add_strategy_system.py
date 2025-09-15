"""add_strategy_system

Revision ID: 2485bb2ff253
Revises: 018_add_missing_updated_at
Create Date: 2025-08-26 09:35:05.814521

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2485bb2ff253"
down_revision: str | Sequence[str] | None = "018_add_missing_updated_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add strategy system tables and columns."""

    # Create strategies table
    op.create_table(
        "strategies",
        sa.Column("strategy_id", sa.String(255), primary_key=True),
        sa.Column("tenant_id", sa.String(50), nullable=True),
        sa.Column("principal_id", sa.String(100), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False, default={}),
        sa.Column("is_simulation", sa.Boolean(), default=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "principal_id"], ["principals.tenant_id", "principals.principal_id"], ondelete="CASCADE"
        ),
        sa.Index("idx_strategies_tenant", "tenant_id"),
        sa.Index("idx_strategies_principal", "tenant_id", "principal_id"),
        sa.Index("idx_strategies_simulation", "is_simulation"),
    )

    # Create strategy_states table for simulation state persistence
    op.create_table(
        "strategy_states",
        sa.Column("strategy_id", sa.String(255), nullable=False),
        sa.Column("state_key", sa.String(255), nullable=False),
        sa.Column("state_value", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("strategy_id", "state_key"),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.strategy_id"], ondelete="CASCADE"),
        sa.Index("idx_strategy_states_id", "strategy_id"),
    )

    # Add strategy_id column to existing tables
    tables_to_update = ["media_buys", "tasks", "audit_logs", "creatives", "creative_associations"]

    # Use batch operations for SQLite compatibility
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    for table_name in tables_to_update:
        # Only modify table if it exists
        if table_name not in existing_tables:
            print(f"⚠️ Skipping {table_name} - table does not exist")
            continue

        # Check if column already exists
        existing_columns = [col["name"] for col in inspector.get_columns(table_name)]
        if "strategy_id" in existing_columns:
            print(f"⚠️ Skipping {table_name}.strategy_id - column already exists")
            continue

        # Add column first
        op.add_column(table_name, sa.Column("strategy_id", sa.String(255), nullable=True))

        # Add index
        op.create_index(f"idx_{table_name}_strategy", table_name, ["strategy_id"])

        # Skip foreign key constraints for SQLite - they'll be enforced at the application level
        # Foreign keys work in PostgreSQL but cause issues in SQLite with ALTER TABLE
        if op.get_bind().engine.name != "sqlite":
            op.create_foreign_key(
                f"fk_{table_name}_strategy",
                table_name,
                "strategies",
                ["strategy_id"],
                ["strategy_id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    """Remove strategy system tables and columns."""

    # Remove strategy_id columns and indexes from existing tables
    tables_to_update = ["media_buys", "tasks", "audit_logs", "creatives", "creative_associations"]

    for table_name in tables_to_update:
        op.drop_constraint(f"fk_{table_name}_strategy", table_name, type_="foreignkey")
        op.drop_index(f"idx_{table_name}_strategy", table_name)
        op.drop_column(table_name, "strategy_id")

    # Drop strategy tables
    op.drop_table("strategy_states")
    op.drop_table("strategies")
