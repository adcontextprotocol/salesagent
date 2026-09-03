"""normalize_webhook_auth_scheme_spellings

Normalizes ``push_notification_configs.authentication_type`` onto the pinned AdCP
``AuthenticationScheme`` vocabulary, so rows that MEAN a supported scheme and merely spell
it differently keep delivering.

PR #1802 makes ``AuthenticationScheme`` the only speller of a webhook auth scheme: two
members, case-sensitive, matched exhaustively at the sender. A stored row spelling anything
else stops delivering until its operator re-registers. That is the intended outcome for a
scheme AdCP 3.1.1 does not define; it is needless for ``bearer`` or ``hmac_sha256``, which
are unambiguously one of the two supported schemes written a different way.

Mapped, case-insensitively:

    bearer, Bearer, BEARER, ...                        -> AuthenticationScheme.Bearer
    hmac, hmac-sha256, hmac_sha256, HMAC_SHA256, ...   -> AuthenticationScheme.HMAC_SHA256

Every other value is left EXACTLY as it is, ``Basic`` and ``NULL`` included. Rewriting
``Basic`` to NULL would silently convert a signed-by-intent registration into an
unauthenticated one; leaving it means those rows refuse and their operator re-registers
deliberately, which is the honest outcome for a scheme the spec does not carry.

Why case-insensitive rather than an exact ``IN`` list: the A2A registration path stores a
FREE-FORM singular ``scheme`` string (``src/a2a_server/adcp_a2a_server.py:154,164``), so
production rows can carry casings this repository never wrote. The seven spellings this
repo's own history contains -- Bearer, bearer, HMAC-SHA256, hmac_sha256, hmac, hmac-sha256,
basic -- are the floor, not the ceiling.

Revision ID: a1f4c7d92b30
Revises: 823974a5553e
Create Date: 2026-08-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from adcp.types import AuthenticationScheme

from alembic import op

revision: str = "a1f4c7d92b30"
down_revision: str | None = "823974a5553e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# The values written are the SDK's own, never literals. The pinned enum is the single
# definition of how a supported scheme is spelled; production reads it, and so does this.
# Restating the strings here -- even to "check" them -- would put the same fact in two
# places, which is the defect this whole change exists to remove: hand-typing the spelling
# is how "hmac_sha256", which nothing in src/ compares against, became a value this codebase
# persisted.
_BEARER = AuthenticationScheme.Bearer.value
_HMAC = AuthenticationScheme.HMAC_SHA256.value

# Everything a row could say and still mean one of the two supported schemes. Compared
# lower-cased against a lower-cased column, so casing variants need no entries here.
_BEARER_SPELLINGS = ("bearer",)
_HMAC_SPELLINGS = ("hmac", "hmac-sha256", "hmac_sha256", "hmacsha256")


def upgrade() -> None:
    """Fold the bearer- and hmac-family spellings onto their canonical members."""
    configs = sa.table(
        "push_notification_configs",
        sa.column("authentication_type", sa.String),
    )

    for canonical, spellings in ((_BEARER, _BEARER_SPELLINGS), (_HMAC, _HMAC_SPELLINGS)):
        op.execute(
            configs.update()
            .where(sa.func.lower(configs.c.authentication_type).in_(spellings))
            .where(configs.c.authentication_type != canonical)
            .values(authentication_type=canonical)
        )


def downgrade() -> None:
    """Deliberately does not restore the original spellings -- it cannot.

    The mapping is lossy in both directions. Three HMAC spellings collapse onto one value,
    so there is no information left to tell a row that said ``hmac`` from one that said
    ``hmac_sha256``; and a row that already said ``Bearer`` before this ran is
    indistinguishable afterwards from one that said ``bearer``.

    Reverting the schema therefore leaves the data normalized, which is safe: the canonical
    spellings are valid input to every version of the code that preceded this migration --
    ``Bearer`` and ``HMAC-SHA256`` are what the pinned spec has always named, and the older
    senders compared case-insensitively or against these same values. Nothing downstream
    breaks by finding a normalized row.

    This is a statement, not an oversight: the completeness guard
    (``tests/unit/test_architecture_migration_completeness.py``) requires a non-empty body
    on every non-merge migration precisely so that "this cannot be undone" is written down
    rather than left as an empty function someone later mistakes for unfinished work.
    """
    op.execute(sa.text("SELECT 1"))
