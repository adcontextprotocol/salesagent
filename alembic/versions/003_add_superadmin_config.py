"""Add superadmin configuration table

Revision ID: 003
Revises: 002
Create Date: 2025-02-04

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    """Add superadmin_config table for global settings."""
    
    # Create superadmin_config table
    op.create_table(
        'superadmin_config',
        sa.Column('config_key', sa.String(100), primary_key=True),
        sa.Column('config_value', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_by', sa.String(255), nullable=True)
    )
    
    # Insert default GAM OAuth config keys
    op.execute("""
        INSERT INTO superadmin_config (config_key, description, config_value) VALUES
        ('gam_oauth_client_id', 'Google Ad Manager OAuth Client ID', NULL),
        ('gam_oauth_client_secret', 'Google Ad Manager OAuth Client Secret', NULL)
    """)


def downgrade():
    """Remove superadmin configuration table."""
    op.drop_table('superadmin_config')