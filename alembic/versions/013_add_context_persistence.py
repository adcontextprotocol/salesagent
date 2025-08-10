"""Add context persistence for A2A/MCP protocols

Revision ID: 013_add_context_persistence
Revises: 012_add_gam_orders_line_items
Create Date: 2025-01-08

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '013_add_context_persistence'
down_revision = '012_add_gam_orders_line_items'
branch_labels = None
depends_on = None


def upgrade():
    """Add contexts table for conversation persistence."""
    
    # Create contexts table
    op.create_table('contexts',
        sa.Column('context_id', sa.String(50), nullable=False),
        sa.Column('tenant_id', sa.String(50), nullable=False),
        sa.Column('principal_id', sa.String(100), nullable=False),
        sa.Column('protocol', sa.String(20), nullable=False),  # 'mcp' or 'a2a'
        sa.Column('state', sa.Text(), nullable=True),  # JSON state data
        sa.Column('metadata', sa.Text(), nullable=True),  # JSON metadata
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('last_accessed_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
        sa.PrimaryKeyConstraint('context_id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id', 'principal_id'], ['principals.tenant_id', 'principals.principal_id'], ondelete='CASCADE')
    )
    
    # Add indexes for efficient lookups
    op.create_index('idx_contexts_tenant_principal', 'contexts', ['tenant_id', 'principal_id'])
    op.create_index('idx_contexts_expires_at', 'contexts', ['expires_at'])
    op.create_index('idx_contexts_last_accessed', 'contexts', ['last_accessed_at'])
    
    # Create context_messages table for conversation history
    op.create_table('context_messages',
        sa.Column('message_id', sa.String(50), nullable=False),
        sa.Column('context_id', sa.String(50), nullable=False),
        sa.Column('sequence_num', sa.Integer(), nullable=False),
        sa.Column('message_type', sa.String(20), nullable=False),  # 'request' or 'response'
        sa.Column('method', sa.String(100), nullable=True),  # The method/tool called
        sa.Column('request_data', sa.Text(), nullable=True),  # JSON request
        sa.Column('response_data', sa.Text(), nullable=True),  # JSON response
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('message_id'),
        sa.ForeignKeyConstraint(['context_id'], ['contexts.context_id'], ondelete='CASCADE'),
        sa.UniqueConstraint('context_id', 'sequence_num', name='uq_context_sequence')
    )
    
    # Add index for efficient message retrieval
    op.create_index('idx_messages_context_seq', 'context_messages', ['context_id', 'sequence_num'])


def downgrade():
    """Remove context persistence tables."""
    op.drop_index('idx_messages_context_seq', table_name='context_messages')
    op.drop_table('context_messages')
    
    op.drop_index('idx_contexts_last_accessed', table_name='contexts')
    op.drop_index('idx_contexts_expires_at', table_name='contexts')
    op.drop_index('idx_contexts_tenant_principal', table_name='contexts')
    op.drop_table('contexts')