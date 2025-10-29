"""add_brand_manifest_policy_to_tenants

Revision ID: 6f05f4179c33
Revises: 319e6b366151
Create Date: 2025-10-28 18:27:53.361639

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6f05f4179c33"
down_revision: str | Sequence[str] | None = "319e6b366151"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add brand_manifest_policy column with default 'require_brand'
    # This preserves existing behavior (strictest policy) for current tenants
    op.add_column(
        "tenants",
        sa.Column(
            "brand_manifest_policy",
            sa.String(50),
            nullable=False,
            server_default="require_brand",
            comment="Brand manifest requirement policy: public (no auth, no pricing), require_auth (auth required, no brand manifest), require_brand (auth + brand manifest required)",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("tenants", "brand_manifest_policy")
