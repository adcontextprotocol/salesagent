"""add_favicon_url_to_tenants

Revision ID: f319ed58b321
Revises: 33e7db3b865f
Create Date: 2026-01-06 07:45:39.237736

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f319ed58b321"
down_revision: Union[str, Sequence[str], None] = "33e7db3b865f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add favicon_url column to tenants table."""
    op.add_column(
        "tenants",
        sa.Column("favicon_url", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    """Remove favicon_url column from tenants table."""
    op.drop_column("tenants", "favicon_url")
