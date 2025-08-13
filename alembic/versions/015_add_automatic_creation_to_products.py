"""Add automatic_creation field to products table

Revision ID: 015_add_automatic_creation_to_products
Revises: 014_add_context_id_to_media_buys
Create Date: 2025-01-13 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '015_auto_creation'
down_revision = '014_add_context_id_to_media_buys'
branch_labels = None
depends_on = None

def upgrade():
    """Add automatic_creation column to products table."""
    
    # Add automatic_creation column to products table (defaults to False for safety)
    with op.batch_alter_table('products') as batch_op:
        batch_op.add_column(sa.Column('automatic_creation', sa.Boolean, nullable=False, server_default='false'))
    
    # Also add automatic_media_buy_creation to tenants table for tenant-level control
    with op.batch_alter_table('tenants') as batch_op:
        batch_op.add_column(sa.Column('automatic_media_buy_creation', sa.Boolean, nullable=False, server_default='false'))

def downgrade():
    """Remove automatic_creation fields."""
    
    # Remove the columns
    with op.batch_alter_table('products') as batch_op:
        batch_op.drop_column('automatic_creation')
    
    with op.batch_alter_table('tenants') as batch_op:
        batch_op.drop_column('automatic_media_buy_creation')