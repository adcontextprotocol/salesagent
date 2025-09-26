"""fix contexts table schema mismatch

Revision ID: fc694918df34
Revises: 023_add_authorized_properties
Create Date: 2025-09-26 07:34:51.331874

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fc694918df34"
down_revision: str | Sequence[str] | None = "023_add_authorized_properties"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Fix contexts table schema to match model definition.

    Production contexts table has incorrect schema. Need to recreate
    with proper columns to match the Context model.
    """
    # First, check if contexts table exists with old schema
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    if "contexts" in inspector.get_table_names():
        # Get current columns
        current_columns = [col["name"] for col in inspector.get_columns("contexts")]

        if "protocol" in current_columns and "conversation_history" not in current_columns:
            # This is the production table with wrong schema - recreate it

            # Drop the old contexts table (preserving any foreign key references)
            op.drop_table("contexts")

            # Create contexts table with correct schema matching the model
            op.create_table(
                "contexts",
                sa.Column("context_id", sa.String(100), primary_key=True),
                sa.Column("tenant_id", sa.String(50), nullable=False),
                sa.Column("principal_id", sa.String(50), nullable=False),
                sa.Column("conversation_history", sa.JSON, nullable=False, server_default="[]"),
                sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
                sa.Column("last_activity_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
                # Foreign key constraints
                sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"], ondelete="CASCADE"),
            )

            # Create indexes
            op.create_index("idx_contexts_tenant", "contexts", ["tenant_id"])
            op.create_index("idx_contexts_principal", "contexts", ["principal_id"])
            op.create_index("idx_contexts_last_activity", "contexts", ["last_activity_at"])

        elif "conversation_history" in current_columns:
            # Table already has correct schema, nothing to do
            pass
    else:
        # Table doesn't exist, create it with correct schema
        op.create_table(
            "contexts",
            sa.Column("context_id", sa.String(100), primary_key=True),
            sa.Column("tenant_id", sa.String(50), nullable=False),
            sa.Column("principal_id", sa.String(50), nullable=False),
            sa.Column("conversation_history", sa.JSON, nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.Column("last_activity_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
            # Foreign key constraints
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"], ondelete="CASCADE"),
        )

        # Create indexes
        op.create_index("idx_contexts_tenant", "contexts", ["tenant_id"])
        op.create_index("idx_contexts_principal", "contexts", ["principal_id"])
        op.create_index("idx_contexts_last_activity", "contexts", ["last_activity_at"])


def downgrade() -> None:
    """Downgrade schema by dropping contexts table."""
    op.drop_index("idx_contexts_last_activity", "contexts")
    op.drop_index("idx_contexts_principal", "contexts")
    op.drop_index("idx_contexts_tenant", "contexts")
    op.drop_table("contexts")
