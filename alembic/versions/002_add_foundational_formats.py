"""Add foundational format support

Revision ID: 002
Revises: 001
Create Date: 2025-01-31

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade():
    """Add extends and is_foundational fields to creative_formats table."""
    
    # Add new columns
    op.add_column('creative_formats', sa.Column('extends', sa.String(50), nullable=True))
    op.add_column('creative_formats', sa.Column('is_foundational', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('creative_formats', sa.Column('modifications', sa.Text(), nullable=True))
    
    # Create index for foundational formats
    op.create_index('idx_creative_formats_foundational', 'creative_formats', ['is_foundational'])
    op.create_index('idx_creative_formats_extends', 'creative_formats', ['extends'])
    
    # Add foreign key constraint for extends field
    op.create_foreign_key(
        'fk_creative_formats_extends',
        'creative_formats', 'creative_formats',
        ['extends'], ['format_id'],
        ondelete='RESTRICT'
    )


def downgrade():
    """Remove foundational format support."""
    
    # Drop foreign key constraint
    op.drop_constraint('fk_creative_formats_extends', 'creative_formats', type_='foreignkey')
    
    # Drop indexes
    op.drop_index('idx_creative_formats_extends', 'creative_formats')
    op.drop_index('idx_creative_formats_foundational', 'creative_formats')
    
    # Drop columns
    op.drop_column('creative_formats', 'modifications')
    op.drop_column('creative_formats', 'is_foundational')
    op.drop_column('creative_formats', 'extends')