"""Add service account authentication for GAM

Revision ID: 47e05de8f5c2
Revises: 02ceecd8d1ab
Create Date: 2025-10-16 06:28:48.939133

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '47e05de8f5c2'
down_revision: Union[str, Sequence[str], None] = '02ceecd8d1ab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add service account JSON field (encrypted)
    op.add_column('adapter_config', sa.Column('gam_service_account_json', sa.Text(), nullable=True))

    # Add auth method field to track which authentication method is being used
    op.add_column('adapter_config', sa.Column('gam_auth_method', sa.String(length=50), nullable=False, server_default='oauth'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('adapter_config', 'gam_auth_method')
    op.drop_column('adapter_config', 'gam_service_account_json')
