"""add protocol to push_notification_configs

Revision ID: 6a52cf43ad75
Revises: a1f4c7d92b30
Create Date: 2026-08-25 04:32:53.394787

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6a52cf43ad75'
down_revision: Union[str, Sequence[str], None] = 'a1f4c7d92b30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Record which protocol a webhook was registered over.

    The delivery scheduler builds its payload with the MCP builder
    unconditionally, so a buyer that registered over A2A receives an MCP-shaped
    delivery report. It had no way to do better: the registration carried url and
    authentication only, and the buyer's protocol was recorded solely into
    workflow metadata at create time, which a periodic job does not read.

    Nullable, and no backfill. A row written before this column existed has no
    honest value to give it -- inventing "mcp" for every historical registration
    would assert something the data never said. Readers treat NULL as "unknown"
    and fall back to the MCP builder, which is exactly today's behaviour, so this
    migration changes nothing on its own (salesagent-pldmk.39).
    """
    op.add_column(
        "push_notification_configs",
        sa.Column("protocol", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    """Drop the column. Nothing depends on it that a NULL would not satisfy."""
    op.drop_column("push_notification_configs", "protocol")
