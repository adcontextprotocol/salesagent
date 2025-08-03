"""Add GAM inventory tables

Revision ID: 003
Revises: 002
Create Date: 2025-01-28

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    # Create gam_inventory table
    op.create_table('gam_inventory',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(length=50), nullable=False),
        sa.Column('inventory_type', sa.String(length=20), nullable=False),
        sa.Column('inventory_id', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('path', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('last_synced', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'inventory_type', 'inventory_id', name='uq_gam_inventory')
    )
    op.create_index('idx_gam_inventory_tenant', 'gam_inventory', ['tenant_id'], unique=False)
    op.create_index('idx_gam_inventory_type', 'gam_inventory', ['inventory_type'], unique=False)
    op.create_index('idx_gam_inventory_status', 'gam_inventory', ['status'], unique=False)
    
    # Create product_inventory_mappings table
    op.create_table('product_inventory_mappings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(length=50), nullable=False),
        sa.Column('product_id', sa.String(length=50), nullable=False),
        sa.Column('inventory_type', sa.String(length=20), nullable=False),
        sa.Column('inventory_id', sa.String(length=50), nullable=False),
        sa.Column('is_primary', sa.Boolean(), nullable=True, default=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id', 'product_id'], ['products.tenant_id', 'products.product_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'product_id', 'inventory_type', 'inventory_id', name='uq_product_inventory')
    )
    op.create_index('idx_product_inventory_mapping', 'product_inventory_mappings', ['tenant_id', 'product_id'], unique=False)


def downgrade():
    op.drop_index('idx_product_inventory_mapping', table_name='product_inventory_mappings')
    op.drop_table('product_inventory_mappings')
    
    op.drop_index('idx_gam_inventory_status', table_name='gam_inventory')
    op.drop_index('idx_gam_inventory_type', table_name='gam_inventory')
    op.drop_index('idx_gam_inventory_tenant', table_name='gam_inventory')
    op.drop_table('gam_inventory')