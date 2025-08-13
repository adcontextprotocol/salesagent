"""Add object lifecycle tracking and improve workflow steps

Revision ID: 015_workflow_improvements
Revises: 014_add_context_persistence
Create Date: 2025-08-11

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '015_workflow_improvements'
down_revision = '014_add_context_persistence'
branch_labels = None
depends_on = None

def upgrade():
    # Create object_workflow_mapping table for lifecycle tracking
    # Check if table already exists
    try:
        op.create_table(
            'object_workflow_mapping',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('object_type', sa.String(50), nullable=False),  # media_buy, creative, product, etc.
            sa.Column('object_id', sa.String(100), nullable=False),   # The actual object's ID
            sa.Column('step_id', sa.String(100), sa.ForeignKey('workflow_steps.step_id', ondelete='CASCADE'), nullable=False),
            sa.Column('action', sa.String(50), nullable=False),        # create, update, approve, reject, etc.
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
        
        # Add indexes for efficient querying
        op.create_index('idx_object_workflow_type_id', 'object_workflow_mapping', ['object_type', 'object_id'])
        op.create_index('idx_object_workflow_step', 'object_workflow_mapping', ['step_id'])
        op.create_index('idx_object_workflow_created', 'object_workflow_mapping', ['created_at'])
    except:
        pass  # Table already exists
    
    # Update workflow_steps table
    try:
        # Remove started_at column
        op.drop_column('workflow_steps', 'started_at')
    except:
        pass  # Column might not exist
    
    try:
        # Add comments field as JSON array
        op.add_column('workflow_steps', 
            sa.Column('comments', sa.JSON(), nullable=False, server_default='[]')
        )
    except:
        pass  # Column might already exist
    
    # Drop the tasks table entirely
    try:
        op.drop_table('tasks')
    except:
        pass  # Table might not exist
    
    # Remove context_id from media_buys since we're using looser association
    # First drop the index that references it
    try:
        op.drop_index('idx_media_buys_context', 'media_buys')
    except:
        pass  # Index might not exist
    op.drop_column('media_buys', 'context_id')

def downgrade():
    # Re-add context_id to media_buys
    op.add_column('media_buys',
        sa.Column('context_id', sa.String(100), nullable=True)
    )
    op.create_foreign_key(
        'fk_media_buys_context',
        'media_buys', 'contexts',
        ['context_id'], ['context_id'],
        ondelete='SET NULL'
    )
    
    # Recreate tasks table (for rollback capability)
    op.create_table(
        'tasks',
        sa.Column('tenant_id', sa.String(50), nullable=False),
        sa.Column('task_id', sa.String(100), nullable=False),
        sa.Column('media_buy_id', sa.String(100), nullable=True),
        sa.Column('task_type', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('context_id', sa.String(100), nullable=True),
        sa.PrimaryKeyConstraint('tenant_id', 'task_id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['context_id'], ['contexts.context_id'], ondelete='SET NULL')
    )
    
    # Remove comments from workflow_steps
    op.drop_column('workflow_steps', 'comments')
    
    # Re-add started_at to workflow_steps
    op.add_column('workflow_steps',
        sa.Column('started_at', sa.DateTime(), nullable=True)
    )
    
    # Drop object_workflow_mapping table
    op.drop_index('idx_object_workflow_created', 'object_workflow_mapping')
    op.drop_index('idx_object_workflow_step', 'object_workflow_mapping')
    op.drop_index('idx_object_workflow_type_id', 'object_workflow_mapping')
    op.drop_table('object_workflow_mapping')