"""merge secure outbound seam and signing heads

Revision ID: 7a24fef449f9
Revises: d5185367920c, e6bb3ee6ae13
Create Date: 2026-09-03 12:13:51.218273

Both parents added schema on disjoint tables, so this converges the graph and does
nothing else. ``d5185367920c`` is this branch's side (RFC 9421 signing: ``signing_keys``,
``adcp_replay``, plus the media-buy status normalization it had already merged);
``e6bb3ee6ae13`` is upstream #1802's own merge revision for the secure-outbound-fetch
work. Neither touches a table the other does, so there is nothing to reconcile beyond
the single head.

``upgrade`` and ``downgrade`` are deliberately empty. The migration-completeness guard
exempts a merge revision precisely BY both bodies being empty
(``scripts/ci/migration_helpers.is_merge_migration``), so adding a no-op DDL statement
to look busy would flip it out of that class and into the downgrade-coverage check with
nothing to cover.
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "7a24fef449f9"
down_revision: str | Sequence[str] | None = ("d5185367920c", "e6bb3ee6ae13")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge point only — both parents' schema is already applied."""
    pass


def downgrade() -> None:
    """Merge point only — nothing to undo."""
    pass
