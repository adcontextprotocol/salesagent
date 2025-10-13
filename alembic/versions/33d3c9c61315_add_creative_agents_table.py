"""Add creative_agents table

Revision ID: 33d3c9c61315
Revises: deb82ef8a598
Create Date: 2025-10-12 23:13:09.036925

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "33d3c9c61315"
down_revision: str | Sequence[str] | None = "deb82ef8a598"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create creative_agents table
    op.create_table(
        "creative_agents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("agent_url", sa.String(length=500), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("auth_type", sa.String(length=50), nullable=True),
        sa.Column("auth_credentials", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index("idx_creative_agents_tenant", "creative_agents", ["tenant_id"])
    op.create_index("idx_creative_agents_enabled", "creative_agents", ["enabled"])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index("idx_creative_agents_enabled", table_name="creative_agents")
    op.drop_index("idx_creative_agents_tenant", table_name="creative_agents")

    # Drop table
    op.drop_table("creative_agents")
