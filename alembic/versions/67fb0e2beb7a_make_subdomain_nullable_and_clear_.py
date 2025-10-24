"""make_subdomain_nullable_and_clear_optable

Revision ID: 67fb0e2beb7a
Revises: e38f2f6f395a
Create Date: 2025-10-24 17:34:31.010250

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '67fb0e2beb7a'
down_revision: Union[str, Sequence[str], None] = 'e38f2f6f395a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Make subdomain nullable and clear optable subdomain to fix SCO-165."""
    # Step 1: Make subdomain nullable
    op.alter_column('tenants', 'subdomain',
                    existing_type=sa.String(length=100),
                    nullable=True)

    # Step 2: Clear the optable subdomain that causes 404 redirects
    # This fixes SCO-165: optable.sales-agent.scope3.com doesn't exist
    op.execute("""
        UPDATE tenants
        SET subdomain = NULL
        WHERE tenant_id = 'optable' AND subdomain = 'optable'
    """)


def downgrade() -> None:
    """Restore subdomain to non-nullable (only if no NULL values exist)."""
    # First, set a default subdomain for any NULL values (use tenant_id)
    op.execute("""
        UPDATE tenants
        SET subdomain = tenant_id
        WHERE subdomain IS NULL
    """)

    # Then make the column non-nullable again
    op.alter_column('tenants', 'subdomain',
                    existing_type=sa.String(length=100),
                    nullable=False)
