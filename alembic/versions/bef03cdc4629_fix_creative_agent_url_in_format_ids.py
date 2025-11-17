"""fix_creative_agent_url_in_format_ids

Revision ID: bef03cdc4629
Revises: b51bbaf5a6ba
Create Date: 2025-11-16 21:26:55.793170

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "bef03cdc4629"
down_revision: Union[str, Sequence[str], None] = "b51bbaf5a6ba"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fix agent URLs in format_ids: creatives → creative."""
    # Update all products with wrong agent URL in format_ids
    op.execute(
        """
        UPDATE products
        SET format_ids = jsonb_set(
            format_ids,
            '{0,agent_url}',
            '"https://creative.adcontextprotocol.org"'
        )
        WHERE format_ids::text LIKE '%creatives.adcontextprotocol.org%'
    """
    )


def downgrade() -> None:
    """Revert agent URLs back to creatives."""
    # Revert the URL change
    op.execute(
        """
        UPDATE products
        SET format_ids = jsonb_set(
            format_ids,
            '{0,agent_url}',
            '"https://creatives.adcontextprotocol.org"'
        )
        WHERE format_ids::text LIKE '%creative.adcontextprotocol.org%'
    """
    )
