"""Add passkey and auth config tables for dynamic authentication.

Revision ID: add_passkey_auth
Revises: add_gam_network_currency
Create Date: 2025-12-28

This migration adds:
1. user_passkeys table - stores WebAuthn credentials for passkey authentication
2. tenant_auth_configs table - stores per-tenant OIDC configuration
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_passkey_auth"
down_revision: str | Sequence[str] | None = "add_gam_network_currency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add user_passkeys and tenant_auth_configs tables."""
    # Create user_passkeys table
    op.create_table(
        "user_passkeys",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.String(50),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            sa.String(50),
            sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
            nullable=False,
        ),
        # WebAuthn credential data
        sa.Column("credential_id", sa.LargeBinary, nullable=False, unique=True),
        sa.Column("public_key", sa.LargeBinary, nullable=False),
        sa.Column("sign_count", sa.Integer, nullable=False, default=0),
        # Metadata
        sa.Column("name", sa.String(100), nullable=False),  # e.g., "MacBook Pro", "YubiKey"
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Indexes for user_passkeys
    op.create_index("idx_user_passkeys_user_id", "user_passkeys", ["user_id"])
    op.create_index("idx_user_passkeys_tenant_id", "user_passkeys", ["tenant_id"])
    op.create_index("idx_user_passkeys_credential_id", "user_passkeys", ["credential_id"], unique=True)

    # Create tenant_auth_configs table
    op.create_table(
        "tenant_auth_configs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id",
            sa.String(50),
            sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        # OIDC configuration
        sa.Column("oidc_enabled", sa.Boolean, nullable=False, default=False),
        sa.Column("oidc_provider", sa.String(50), nullable=True),  # google, microsoft, custom
        sa.Column("oidc_discovery_url", sa.String(500), nullable=True),
        sa.Column("oidc_client_id", sa.String(500), nullable=True),
        sa.Column("oidc_client_secret_encrypted", sa.Text, nullable=True),  # Fernet encrypted
        sa.Column("oidc_scopes", sa.String(500), nullable=True, default="openid email profile"),
        # Verification state
        sa.Column("oidc_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("oidc_verified_redirect_uri", sa.String(500), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now(), nullable=True),
    )

    # Index for tenant_auth_configs
    op.create_index("idx_tenant_auth_configs_tenant_id", "tenant_auth_configs", ["tenant_id"], unique=True)


def downgrade() -> None:
    """Remove user_passkeys and tenant_auth_configs tables."""
    # Drop tenant_auth_configs
    op.drop_index("idx_tenant_auth_configs_tenant_id", table_name="tenant_auth_configs")
    op.drop_table("tenant_auth_configs")

    # Drop user_passkeys
    op.drop_index("idx_user_passkeys_credential_id", table_name="user_passkeys")
    op.drop_index("idx_user_passkeys_tenant_id", table_name="user_passkeys")
    op.drop_index("idx_user_passkeys_user_id", table_name="user_passkeys")
    op.drop_table("user_passkeys")
