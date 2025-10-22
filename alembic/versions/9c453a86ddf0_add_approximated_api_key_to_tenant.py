"""add_approximated_api_key_to_tenant

Revision ID: 9c453a86ddf0
Revises: ed7d05fea3be
Create Date: 2025-10-22 03:49:12.175678

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c453a86ddf0"
down_revision: str | Sequence[str] | None = "ed7d05fea3be"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("tenants", sa.Column("approximated_api_key", sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("tenants", "approximated_api_key")
