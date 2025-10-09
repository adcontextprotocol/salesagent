"""add_webhook_secret_to_push_notification_configs

Revision ID: 62bc22421983
Revises: 8ee085776997
Create Date: 2025-10-09 11:37:38.271669

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "62bc22421983"
down_revision: str | Sequence[str] | None = "8ee085776997"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add webhook_secret column for HMAC-SHA256 signatures."""
    op.add_column("push_notification_configs", sa.Column("webhook_secret", sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Remove webhook_secret column."""
    op.drop_column("push_notification_configs", "webhook_secret")
