"""add_agent_url_to_creatives_and_products

Revision ID: f2addf453200
Revises: 2a2aaed3b50d
Create Date: 2025-10-13 20:46:44.896217

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2addf453200'
down_revision: Union[str, Sequence[str], None] = '2a2aaed3b50d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to support AdCP v2.4 format_id namespacing.

    Changes:
    1. Add agent_url column to creatives table for format_id namespacing
    2. Set default agent_url for existing creatives (reference implementation)
    3. Drop deprecated creative_formats table (no longer used)

    Note: Products table formats are stored as JSONB and will be migrated
    via a data migration script separately.
    """
    # Add agent_url column to creatives table
    op.add_column(
        'creatives',
        sa.Column('agent_url', sa.String(500), nullable=True)
    )

    # Set default agent_url for existing creatives to AdCP reference implementation
    # This is the standard agent URL for foundational formats
    op.execute("""
        UPDATE creatives
        SET agent_url = 'https://creative.adcontextprotocol.org'
        WHERE agent_url IS NULL
    """)

    # Make agent_url non-nullable after backfilling
    op.alter_column('creatives', 'agent_url', nullable=False)

    # Add index on (agent_url, format) for format lookups
    op.create_index(
        'idx_creatives_format_namespace',
        'creatives',
        ['agent_url', 'format']
    )

    # Drop deprecated creative_formats table
    # This table is no longer used - sales agents fetch formats from creative agents via AdCP
    op.drop_table('creative_formats')


def downgrade() -> None:
    """Downgrade schema."""
    # Recreate creative_formats table (basic structure, data cannot be restored)
    op.create_table(
        'creative_formats',
        sa.Column('format_id', sa.String(50), primary_key=True),
        sa.Column('tenant_id', sa.String(50), nullable=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('type', sa.String(20), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('width', sa.Integer),
        sa.Column('height', sa.Integer),
        sa.Column('duration_seconds', sa.Integer),
        sa.Column('max_file_size_kb', sa.Integer),
        sa.Column('specs', sa.JSON, nullable=False),
        sa.Column('is_standard', sa.Boolean, default=True),
        sa.Column('is_foundational', sa.Boolean, default=False),
        sa.Column('extends', sa.String(50), nullable=True),
        sa.Column('modifications', sa.JSON, nullable=True),
        sa.Column('source_url', sa.Text),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )

    # Drop index
    op.drop_index('idx_creatives_format_namespace', 'creatives')

    # Remove agent_url column from creatives
    op.drop_column('creatives', 'agent_url')
