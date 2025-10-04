"""add_creative_assignments_table

Revision ID: e17d03b0a79e
Revises: f4f0feaaedff
Create Date: 2025-10-04 07:58:13.474472

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e17d03b0a79e"
down_revision: str | Sequence[str] | None = "f4f0feaaedff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "creative_assignments",
        sa.Column("assignment_id", sa.String(length=100), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("creative_id", sa.String(length=100), nullable=False),
        sa.Column("media_buy_id", sa.String(length=100), nullable=False),
        sa.Column("package_id", sa.String(length=100), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["creative_id"], ["creatives.creative_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["media_buy_id"], ["media_buys.media_buy_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("assignment_id"),
        sa.UniqueConstraint("tenant_id", "creative_id", "media_buy_id", "package_id", name="uq_creative_assignment"),
    )
    op.create_index("idx_creative_assignments_tenant", "creative_assignments", ["tenant_id"])
    op.create_index("idx_creative_assignments_creative", "creative_assignments", ["creative_id"])
    op.create_index("idx_creative_assignments_media_buy", "creative_assignments", ["media_buy_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_creative_assignments_media_buy", table_name="creative_assignments")
    op.drop_index("idx_creative_assignments_creative", table_name="creative_assignments")
    op.drop_index("idx_creative_assignments_tenant", table_name="creative_assignments")
    op.drop_table("creative_assignments")
