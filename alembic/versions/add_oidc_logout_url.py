"""Add oidc_logout_url to tenant_auth_configs table.

Revision ID: add_oidc_logout_url
Revises: add_auth_setup_mode
Create Date: 2026-01-01

Adds optional IdP logout URL field for proper OIDC logout support.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_oidc_logout_url"
down_revision: str | Sequence[str] | None = "add_auth_setup_mode"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add oidc_logout_url column to tenant_auth_configs."""
    op.add_column(
        "tenant_auth_configs",
        sa.Column("oidc_logout_url", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    """Remove oidc_logout_url column from tenant_auth_configs."""
    op.drop_column("tenant_auth_configs", "oidc_logout_url")
