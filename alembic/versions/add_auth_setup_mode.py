"""Add auth_setup_mode column to tenants table.

Revision ID: add_auth_setup_mode
Revises: add_passkey_auth
Create Date: 2025-12-30

New tenants start in auth setup mode (test credentials work).
Admin configures SSO, tests it, then disables setup mode.
Once disabled, only SSO authentication works.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_auth_setup_mode"
down_revision: str | Sequence[str] | None = "add_tenant_auth_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add auth_setup_mode column to tenants table."""
    op.add_column(
        "tenants",
        sa.Column("auth_setup_mode", sa.Boolean, nullable=False, server_default="true"),
    )


def downgrade() -> None:
    """Remove auth_setup_mode column from tenants table."""
    op.drop_column("tenants", "auth_setup_mode")
