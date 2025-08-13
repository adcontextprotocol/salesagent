"""Add context_id to media_buys table

Revision ID: 014_add_context_id_to_media_buys
Revises: 013_principal_advertiser_mapping
Create Date: 2025-01-13 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '014_add_context_id_to_media_buys'
down_revision = '013_principal_advertiser_mapping'
branch_labels = None
depends_on = None

def upgrade():
    """Add context_id column to media_buys table for AdCP spec compliance."""
    
    # Add context_id column to media_buys table
    with op.batch_alter_table('media_buys') as batch_op:
        batch_op.add_column(sa.Column('context_id', sa.String(50), nullable=True))
    
    # Create an index on context_id for faster lookups
    op.create_index('idx_media_buys_context_id', 'media_buys', ['context_id'])
    
    # Update existing media_buys with generated context IDs
    connection = op.get_bind()
    result = connection.execute(sa.text("SELECT media_buy_id FROM media_buys WHERE context_id IS NULL"))
    for row in result:
        # Generate a context_id for existing media buys
        import uuid
        context_id = f"ctx_{uuid.uuid4().hex[:12]}"
        connection.execute(
            sa.text("UPDATE media_buys SET context_id = :context_id WHERE media_buy_id = :media_buy_id"),
            {"context_id": context_id, "media_buy_id": row[0]}
        )

def downgrade():
    """Remove context_id column from media_buys table."""
    
    # Drop the index first
    op.drop_index('idx_media_buys_context_id')
    
    # Remove the column
    with op.batch_alter_table('media_buys') as batch_op:
        batch_op.drop_column('context_id')