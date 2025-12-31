"""add_product_ranking_prompt_to_tenants

Revision ID: 58e9d3fdf1f6
Revises: 498429a885ac
Create Date: 2025-12-31 00:32:39.155368

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "58e9d3fdf1f6"
down_revision: Union[str, Sequence[str], None] = "498429a885ac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add product_ranking_prompt column to tenants table."""
    op.add_column(
        "tenants",
        sa.Column("product_ranking_prompt", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Remove product_ranking_prompt column from tenants table."""
    op.drop_column("tenants", "product_ranking_prompt")
