"""change_brand_manifest_policy_default_to_require_auth

Revision ID: 378299ad502f
Revises: 6f05f4179c33
Create Date: 2025-10-29 02:52:27.162501

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "378299ad502f"
down_revision: str | Sequence[str] | None = "6f05f4179c33"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema - change brand_manifest_policy default to require_auth.

    This reflects the correct default for most publishers: standard B2B model
    where advertisers must sign up to see products and pricing.

    Existing tenants keep their current settings (no data migration).
    """
    # Change the server default for new tenants
    op.alter_column(
        "tenants",
        "brand_manifest_policy",
        server_default="require_auth",
        existing_type=sa.String(50),
        existing_nullable=False,
        comment="Product discovery access policy: require_auth (standard B2B - signup to see pricing), require_brand (brand context required for bespoke products), public (generic products visible to all)",
    )


def downgrade() -> None:
    """Downgrade schema - revert to require_brand default."""
    op.alter_column(
        "tenants",
        "brand_manifest_policy",
        server_default="require_brand",
        existing_type=sa.String(50),
        existing_nullable=False,
        comment="Brand manifest requirement policy: public (no auth, no pricing), require_auth (auth required, no brand manifest), require_brand (auth + brand manifest required)",
    )
