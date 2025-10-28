"""add_adcp_creative_fields

Adds full AdCP v1 creative-asset schema compliance to creatives table:
- format_id split into agent_url and id components (AdCP v2.4+ FormatId structure)
- assets JSONB field for structured asset storage per AdCP spec
- inputs JSONB array for generative format preview contexts
- tags JSONB array for user-defined organization tags
- approved boolean flag for generative creative workflow

Migration strategy:
- Existing data in 'data' JSONB preserved for backward compatibility
- New 'assets' field populated from existing data where possible
- Indexes added for common query patterns (format lookups, tag searches)

Revision ID: 4bac9efe56fc
Revises: 319e6b366151
Create Date: 2025-10-28 15:10:33.845025

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from src.core.database.json_type import JSONType

# revision identifiers, used by Alembic.
revision: str = '4bac9efe56fc'
down_revision: Union[str, Sequence[str], None] = '319e6b366151'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add AdCP v1 creative-asset schema fields."""

    # Add new columns for AdCP compliance
    # format_id components (AdCP v2.4+ FormatId structure)
    op.add_column('creatives', sa.Column('format_id_agent_url', sa.String(500), nullable=True))
    op.add_column('creatives', sa.Column('format_id_id', sa.String(100), nullable=True))

    # AdCP creative-asset required/optional fields
    op.add_column('creatives', sa.Column('assets', JSONType, nullable=True,
                                         comment='Assets keyed by asset_role per AdCP spec'))
    op.add_column('creatives', sa.Column('inputs', JSONType, nullable=True,
                                         comment='Preview contexts for generative formats (AdCP spec)'))
    op.add_column('creatives', sa.Column('tags', JSONType, nullable=True,
                                         comment='User-defined tags array (AdCP spec)'))
    op.add_column('creatives', sa.Column('approved', sa.Boolean, nullable=True,
                                         comment='Approval flag for generative creatives (AdCP spec)'))

    # Migrate existing data: split format field into format_id components
    # Default to AdCP reference implementation for agent_url if not already namespaced
    op.execute("""
        UPDATE creatives
        SET format_id_agent_url = COALESCE(
            (data->>'agent_url'),
            'https://creative.adcontextprotocol.org'
        ),
        format_id_id = format
        WHERE format_id_agent_url IS NULL
    """)

    # Migrate existing data: populate assets from data field if structured correctly
    # This handles creatives that already have assets in the data JSONB
    op.execute("""
        UPDATE creatives
        SET assets = data->'assets'
        WHERE data ? 'assets' AND assets IS NULL
    """)

    # Migrate existing data: populate tags from data field if present
    op.execute("""
        UPDATE creatives
        SET tags = data->'tags'
        WHERE data ? 'tags' AND tags IS NULL
    """)

    # Create indexes for common query patterns
    op.create_index('idx_creatives_format_agent_url', 'creatives', ['format_id_agent_url'])
    op.create_index('idx_creatives_format_id', 'creatives', ['format_id_id'])
    op.create_index('idx_creatives_tags', 'creatives', ['tags'],
                   postgresql_using='gin',
                   postgresql_where=sa.text('tags IS NOT NULL'))
    op.create_index('idx_creatives_approved', 'creatives', ['approved'],
                   postgresql_where=sa.text('approved IS NOT NULL'))


def downgrade() -> None:
    """Remove AdCP creative-asset fields (preserves data in 'data' JSONB)."""

    # Drop indexes
    op.drop_index('idx_creatives_approved', 'creatives')
    op.drop_index('idx_creatives_tags', 'creatives')
    op.drop_index('idx_creatives_format_id', 'creatives')
    op.drop_index('idx_creatives_format_agent_url', 'creatives')

    # Before dropping columns, preserve data back to 'data' JSONB if needed
    op.execute("""
        UPDATE creatives
        SET data = jsonb_set(
            jsonb_set(
                jsonb_set(
                    COALESCE(data, '{}'::jsonb),
                    '{assets}', COALESCE(assets, 'null'::jsonb)
                ),
                '{tags}', COALESCE(tags, 'null'::jsonb)
            ),
            '{agent_url}', to_jsonb(format_id_agent_url)
        )
        WHERE assets IS NOT NULL OR tags IS NOT NULL OR format_id_agent_url IS NOT NULL
    """)

    # Drop columns
    op.drop_column('creatives', 'approved')
    op.drop_column('creatives', 'tags')
    op.drop_column('creatives', 'inputs')
    op.drop_column('creatives', 'assets')
    op.drop_column('creatives', 'format_id_id')
    op.drop_column('creatives', 'format_id_agent_url')
