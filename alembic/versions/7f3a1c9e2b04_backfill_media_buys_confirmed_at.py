"""Backfill media_buys.confirmed_at for rows that predate the column.

`2c4e6a7b8d9e` added the column nullable and left historical rows NULL. That left
production reading a NULL it could not legitimately report: the pinned
get-media-buys-response schema forbids an item whose status is `active` from
carrying a null `confirmed_at`, so those rows could only be served by inventing a
value at read time.

Inventing it at read time is the wrong fix. A nullable column that production
cannot legitimately read as NULL is a DATA defect, and data defects are corrected
by migration — not by a compatibility branch that every later reader has to know
about and that never gets deleted.

So this backfills once, using the same rule the read-time fallback encoded and
that PR #1544 defines for the field: the approval instant on the manual-approval
path, creation on the synchronous auto-approve path. After it runs, no
seller-confirmed row has a NULL `confirmed_at`, and the read path can simply emit
the column.

The status partition is written out literally rather than imported from
`models._SELLER_COMMITTED_STATUSES`: a migration records what was true when it
ran, and must not change meaning later because application code moved a status
from one side of the partition to the other.

The COMMITTED side is the one written out, and the predicate matches on it
POSITIVELY. Selecting by the complement (`NOT IN (<unconfirmed>)`) looks
equivalent and is not: it makes "committed" the DEFAULT for any value in neither
list, so a legacy row carrying a status this vocabulary never had — the only kind
of row a backfill exists to meet — would be stamped with a seller-commitment
instant nobody ever observed. That is the outcome `models.py` forbids where it
argues the same partition fail-closed. A status in neither list is left NULL,
which is also what the status-normalising migration beside this one then
resolves.

Not backfilled, deliberately: rows in an unconfirmed status (`draft`, `pending`,
`pending_approval`, `rejected`, `failed`, `pending_creatives`) have no commitment
instant to record, so NULL is their correct value rather than missing data.

`pending_creatives` is on that list for the same reason it is absent from
`models._SELLER_COMMITTED_STATUSES`: it is a hold awaiting creative approval, the
ad server has not been contacted, and the pin describes confirmed_at as null in
manual-approval flows until commitment occurs. Backfilling it would manufacture a
commitment instant nobody observed -- the outcome the paragraph above forbids --
for every held row already in the table. Changed before release: this migration
has never shipped, so the freeze it describes has nothing to protect yet.

Revision ID: 7f3a1c9e2b04
Revises: 2c4e6a7b8d9e
"""

import sqlalchemy as sa
from alembic import op

revision = "7f3a1c9e2b04"
down_revision = "2c4e6a7b8d9e"
branch_labels = None
depends_on = None

# Frozen at authoring time — see the module docstring. The COMMITTED side is
# listed, so a value in neither partition is NOT backfilled.
_COMMITTED_STATUSES = (
    "active",
    "approved",
    "ready",
    "scheduled",
    "pending_activation",
    "pending_start",
    "paused",
    "completed",
    "canceled",
)


def upgrade() -> None:
    """Set confirmed_at on every seller-confirmed row that is missing it."""
    op.execute(
        sa.text(
            """
            UPDATE media_buys
               SET confirmed_at = COALESCE(approved_at, created_at)
             WHERE confirmed_at IS NULL
               AND lower(status) IN :committed
               AND COALESCE(approved_at, created_at) IS NOT NULL
            """
        ).bindparams(sa.bindparam("committed", value=_COMMITTED_STATUSES, expanding=True))
    )


def downgrade() -> None:
    """Re-NULL the backfilled rows.

    Cannot be exact: a row stamped by this backfill is indistinguishable from one
    the repository stamped at the same instant. The condition below is the closest
    honest inverse — clear `confirmed_at` only where it still equals the value this
    migration would have written, so rows carrying a genuinely observed commitment
    instant are left alone.
    """
    op.execute(
        sa.text(
            """
            UPDATE media_buys
               SET confirmed_at = NULL
             WHERE confirmed_at IS NOT NULL
               AND confirmed_at = COALESCE(approved_at, created_at)
               AND lower(status) IN :committed
            """
        ).bindparams(sa.bindparam("committed", value=_COMMITTED_STATUSES, expanding=True))
    )
