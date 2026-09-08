"""Integration test for a1f4c7d92b30 — normalize webhook auth scheme spellings.

PR #1802 makes ``AuthenticationScheme`` the only speller of a webhook auth scheme, matched
case-sensitively at the sender. A stored row spelling anything else stops delivering. The
migration folds the spellings that unambiguously MEAN a supported scheme onto the canonical
member, so those rows keep working; everything else is left exactly as it is.

The two halves are graded separately on purpose, because they fail differently:

* Under-mapping (a ``hmac_sha256`` row left alone) silently stops a buyer's webhooks.
* Over-mapping (a ``Basic`` row rewritten) silently converts a signed-by-intent
  registration into an unauthenticated one — strictly worse, and invisible.

Every historical spelling seeded here was measured from this repo's own git history for
values written into the column by ``src/``: Bearer, bearer, HMAC-SHA256, hmac_sha256, hmac,
hmac-sha256, basic. The mixed-case rows are not from that history — the A2A path stores a
FREE-FORM scheme string (``src/a2a_server/adcp_a2a_server.py:154,164``), so production can
hold casings this repository never wrote, and the migration matches case-insensitively for
exactly that reason.
"""

import pytest
from adcp.types import AuthenticationScheme
from sqlalchemy import text

from tests.integration.migration_helpers import run_alembic_downgrade, run_alembic_upgrade

NORMALIZE_REV = "a1f4c7d92b30"
PRE_NORMALIZE_REV = "823974a5553e"

# The canonical values come from the SDK, never literals — the same rule the migration
# itself follows, so a rename breaks both together rather than letting the test keep
# asserting a value production no longer writes.
BEARER = AuthenticationScheme.Bearer.value
HMAC = AuthenticationScheme.HMAC_SHA256.value

# (row id, stored spelling, expected value after the migration)
CASES = [
    # --- bearer family: every one folds onto Bearer -------------------------------------
    ("pnc_bearer_lower", "bearer", BEARER),
    ("pnc_bearer_canonical", BEARER, BEARER),
    ("pnc_bearer_upper", "BEARER", BEARER),
    ("pnc_bearer_mixed", "BeArEr", BEARER),
    # --- hmac family: every one folds onto HMAC-SHA256 -----------------------------------
    ("pnc_hmac_canonical", HMAC, HMAC),
    ("pnc_hmac_underscore", "hmac_sha256", HMAC),
    ("pnc_hmac_underscore_upper", "HMAC_SHA256", HMAC),
    ("pnc_hmac_hyphen_lower", "hmac-sha256", HMAC),
    ("pnc_hmac_bare", "hmac", HMAC),
    ("pnc_hmac_noseparator", "hmacsha256", HMAC),
    # --- untouched: not a supported scheme, so the operator re-registers deliberately ----
    ("pnc_basic_canonical", "Basic", "Basic"),
    ("pnc_basic_lower", "basic", "basic"),
    ("pnc_unknown", "oauth2", "oauth2"),
    ("pnc_empty_string", "", ""),
    # --- untouched: an unauthenticated registration stays unauthenticated ----------------
    ("pnc_null", None, None),
]


def _seed(engine):
    """Insert one config row per historical spelling, plus the rows that must not move."""
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO tenants (tenant_id, name, subdomain, created_at, updated_at) "
                "VALUES ('tenant_authnorm', 'Auth Norm Tenant', 'authnorm-test', NOW(), NOW())"
            )
        )
        # push_notification_configs carries a COMPOSITE foreign key on
        # (tenant_id, principal_id), so the principal has to exist first.
        conn.execute(
            text(
                "INSERT INTO principals "
                "(tenant_id, principal_id, name, platform_mappings, access_token) "
                "VALUES ('tenant_authnorm', 'principal_authnorm', 'Auth Norm Principal', "
                "'{}'::jsonb, 'token-authnorm')"
            )
        )
        for row_id, stored, _expected in CASES:
            conn.execute(
                text(
                    "INSERT INTO push_notification_configs "
                    "(id, tenant_id, principal_id, url, authentication_type, authentication_token) "
                    "VALUES (:id, 'tenant_authnorm', 'principal_authnorm', :url, :scheme, 'credential-value')"
                ),
                {"id": row_id, "url": f"https://buyer.example/{row_id}", "scheme": stored},
            )
        conn.commit()


def _scheme(engine, row_id):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT authentication_type FROM push_notification_configs WHERE id = :id"),
            {"id": row_id},
        ).fetchone()
        return row[0] if row else None


def _token(engine, row_id):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT authentication_token FROM push_notification_configs WHERE id = :id"),
            {"id": row_id},
        ).fetchone()
        return row[0] if row else None


@pytest.mark.requires_db
class TestWebhookAuthSchemeNormalization:
    """a1f4c7d92b30 folds supported-scheme spellings and leaves everything else alone."""

    def test_upgrade_folds_every_bearer_spelling(self, migration_db):
        """bearer / Bearer / BEARER / BeArEr all become the canonical Bearer."""
        engine, db_url = migration_db

        run_alembic_upgrade(db_url, PRE_NORMALIZE_REV)
        _seed(engine)

        # The spellings really are unnormalized before the migration runs — without this the
        # test would pass against a database where nothing happened.
        assert _scheme(engine, "pnc_bearer_lower") == "bearer"
        assert _scheme(engine, "pnc_hmac_underscore") == "hmac_sha256"

        run_alembic_upgrade(db_url, NORMALIZE_REV)

        for row_id, _stored, expected in CASES:
            if expected == BEARER:
                assert _scheme(engine, row_id) == BEARER, f"{row_id} did not fold onto {BEARER}"

    def test_upgrade_folds_every_hmac_spelling(self, migration_db):
        """Every hmac variant, separator and casing included, becomes HMAC-SHA256."""
        engine, _ = migration_db
        for row_id, _stored, expected in CASES:
            if expected == HMAC:
                assert _scheme(engine, row_id) == HMAC, f"{row_id} did not fold onto {HMAC}"

    def test_upgrade_leaves_basic_exactly_as_it_was(self, migration_db):
        """Basic is not in AdCP 3.1.1, so it is not ours to rewrite.

        Rewriting it to NULL would turn a registration whose operator asked for
        authentication into one that delivers unsigned. Refusing it and letting the operator
        re-register is the honest outcome, so the migration must not touch these rows.
        """
        engine, _ = migration_db
        assert _scheme(engine, "pnc_basic_canonical") == "Basic"
        assert _scheme(engine, "pnc_basic_lower") == "basic"

    def test_upgrade_leaves_unrecognised_and_empty_values_alone(self, migration_db):
        """A scheme the migration does not recognise is not guessed at."""
        engine, _ = migration_db
        assert _scheme(engine, "pnc_unknown") == "oauth2"
        assert _scheme(engine, "pnc_empty_string") == ""

    def test_upgrade_leaves_unauthenticated_rows_unauthenticated(self, migration_db):
        """A NULL scheme means no authentication, and stays that way."""
        engine, _ = migration_db
        assert _scheme(engine, "pnc_null") is None

    def test_upgrade_touches_no_column_but_the_scheme(self, migration_db):
        """The credential is not rewritten, reformatted or dropped along the way."""
        engine, _ = migration_db
        for row_id, _stored, _expected in CASES:
            assert _token(engine, row_id) == "credential-value", f"{row_id} lost its credential"

    def test_upgrade_loses_no_rows(self, migration_db):
        """An UPDATE, never a DELETE — every seeded row still exists."""
        engine, _ = migration_db
        with engine.connect() as conn:
            count = conn.execute(
                text("SELECT COUNT(*) FROM push_notification_configs WHERE tenant_id = 'tenant_authnorm'")
            ).scalar()
        assert count == len(CASES)

    def test_downgrade_leaves_the_data_normalized(self, migration_db):
        """Downgrade cannot un-normalize, and says so — this pins that it does not try.

        Three hmac spellings collapse onto one value, so the original is unrecoverable. The
        canonical spellings are valid input to every version that preceded this migration,
        so leaving them normalized is safe; silently inventing a spelling to 'restore' would
        not be.
        """
        engine, db_url = migration_db

        run_alembic_downgrade(db_url, PRE_NORMALIZE_REV)

        assert _scheme(engine, "pnc_bearer_lower") == BEARER
        assert _scheme(engine, "pnc_hmac_underscore") == HMAC
        assert _scheme(engine, "pnc_basic_canonical") == "Basic"
        assert _scheme(engine, "pnc_null") is None
