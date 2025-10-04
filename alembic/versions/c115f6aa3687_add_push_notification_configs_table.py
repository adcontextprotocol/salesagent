"""add_push_notification_configs_table

Revision ID: c115f6aa3687
Revises: 574ecf3d98c7
Create Date: 2025-10-03 10:46:55.646167

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c115f6aa3687"
down_revision: str | Sequence[str] | None = "574ecf3d98c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create push_notification_configs table
    op.create_table(
        "push_notification_configs",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("principal_id", sa.String(50), nullable=False),
        sa.Column("session_id", sa.String(100), nullable=True),  # Optional A2A session tracking
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("authentication_type", sa.String(50), nullable=True),  # bearer, basic, none
        sa.Column("authentication_token", sa.Text, nullable=True),
        sa.Column("validation_token", sa.Text, nullable=True),  # For validating webhook ownership
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "principal_id"], ["principals.tenant_id", "principals.principal_id"], ondelete="CASCADE"
        ),
    )

    # Create indexes for efficient lookups
    op.create_index("idx_push_notification_configs_tenant", "push_notification_configs", ["tenant_id"])
    op.create_index(
        "idx_push_notification_configs_principal", "push_notification_configs", ["tenant_id", "principal_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_push_notification_configs_principal", "push_notification_configs")
    op.drop_index("idx_push_notification_configs_tenant", "push_notification_configs")
    op.drop_table("push_notification_configs")
