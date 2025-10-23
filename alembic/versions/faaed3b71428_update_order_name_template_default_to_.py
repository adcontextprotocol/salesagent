"""Update order_name_template default to use brand_name instead of promoted_offering

Revision ID: faaed3b71428
Revises: ed7d05fea3be
Create Date: 2025-10-22 21:34:50.416702

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "faaed3b71428"
down_revision: str | Sequence[str] | None = "ed7d05fea3be"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Update the server_default for order_name_template column
    # Change from promoted_offering to brand_name per AdCP v2.2.0 spec
    op.alter_column(
        "tenants", "order_name_template", server_default="{campaign_name|brand_name} - {buyer_ref} - {date_range}"
    )

    # Update existing rows that have the old template
    # This is a data migration - update ALL tenants with promoted_offering references
    # Using aggressive approach: update all rows, not just matching ones
    op.execute(
        """
        UPDATE tenants
        SET order_name_template = REPLACE(COALESCE(order_name_template, ''), 'promoted_offering', 'brand_name')
        WHERE order_name_template IS NULL
           OR order_name_template LIKE '%promoted_offering%'
           OR order_name_template = ''
        """
    )

    # Set proper default for any remaining NULL or empty templates
    op.execute(
        """
        UPDATE tenants
        SET order_name_template = '{campaign_name|brand_name} - {buyer_ref} - {date_range}'
        WHERE order_name_template IS NULL
           OR order_name_template = ''
           OR order_name_template = 'N/A'
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Revert to old template (for rollback purposes only)
    op.alter_column(
        "tenants",
        "order_name_template",
        server_default="{campaign_name|promoted_offering} - {buyer_ref} - {date_range}",
    )
