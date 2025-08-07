"""Add superadmin API key support

Revision ID: 011_add_superadmin_api_key
Revises: 010_add_sync_tracking
Create Date: 2025-01-06

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime


# revision identifiers, used by Alembic.
revision = '011_add_superadmin_api_key'
down_revision = '010_add_sync_tracking'
branch_labels = None
depends_on = None


def upgrade():
    """
    Add support for superadmin API key authentication.
    The superadmin_config table already exists from previous migrations.
    """
    # Check if we need to add a default description for the API key config
    # This is just a placeholder - the actual API key will be generated via the API
    pass


def downgrade():
    """
    Remove superadmin API key support.
    We don't actually remove anything from the table as it's a generic config table.
    """
    pass