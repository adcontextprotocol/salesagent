"""add_auth_header_and_timeout_to_creative_agents

Revision ID: d169f2e66919
Revises: c34b078f4e8a
Create Date: 2025-11-07 06:46:45.116343

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d169f2e66919"
down_revision: str | Sequence[str] | None = "c34b078f4e8a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema: Add auth_header and timeout columns to creative_agents table."""
    # Add auth_header column (nullable, matching SignalsAgent)
    op.add_column("creative_agents", sa.Column("auth_header", sa.String(length=100), nullable=True))

    # Add timeout column (not nullable, with default value)
    op.add_column("creative_agents", sa.Column("timeout", sa.Integer(), nullable=False, server_default="30"))


def downgrade() -> None:
    """Downgrade schema: Remove auth_header and timeout columns from creative_agents table."""
    op.drop_column("creative_agents", "timeout")
    op.drop_column("creative_agents", "auth_header")
