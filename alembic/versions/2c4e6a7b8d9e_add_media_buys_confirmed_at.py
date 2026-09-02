"""Add the seller confirmation instant for media buys.

AdCP 3.1.1 `confirmed_at` — the moment the seller committed to running the buy,
written once and stable across later transitions. Nullable because the spec
permits null for the arms where the seller has not committed yet
(draft, pending, pending_approval, rejected, failed) — i.e. every status OUTSIDE
`models._SELLER_COMMITTED_STATUSES`, which is the list that is written out and the
one `is_media_buy_seller_confirmed` consults.

Historical rows are left NULL rather than backfilled here: a large data rewrite
does not belong in a single Alembic transaction, and NULL is the honest value —
we cannot reconstruct a commitment instant we never recorded. Existing rows
therefore read as unconfirmed until their next status transition stamps them.

Cherry-picked from PR #1544 (which pairs it with an operational backfill script
that is NOT part of this slice).

Revision ID: 2c4e6a7b8d9e
Revises: 1497aa06013c
Create Date: 2026-07-03 13:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "2c4e6a7b8d9e"
down_revision: str | Sequence[str] | None = "1497aa06013c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add media_buys.confirmed_at."""
    op.add_column("media_buys", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Drop media_buys.confirmed_at."""
    op.drop_column("media_buys", "confirmed_at")
