"""The push-notification repository persists the VALUE, and preserves what it was not passed.

Two obligations, one module, because they are the two halves of ``upsert``'s
parameter list and neither is safe alone.

**The receipt half.** Epic D lane C2 (salesagent-fo99.2).
``ValidatedWebhookRegistration`` is the receipt that BOTH ingest preconditions
ran — the registration SSRF gate on the URL half and the pinned
``Authentication`` model built inside ``_accept`` on the credential half. Before
this lane the receipt evaporated at the persistence boundary: ``upsert`` took
``url`` / ``authentication_type`` / ``authentication_token`` as three unrelated
strings, so a caller that had never run either gate type-checked exactly like a
caller that had. The repository compensated by re-validating the URL itself
("defense-in-depth"), which is the shape this lane deletes: a value that exists
passed the gate, so the type is the receipt and there is nothing left to
re-check.

Why the signature case is an assertion and not a code-review note: the
compensating move under review pressure is to ADD a value-taking overload
beside the string-taking one, which leaves every unreceipted call site
type-checking exactly as it does today. ``_RAW_STRING_PARAMS`` is therefore
asserted ABSENT, not merely "a registration parameter is present" — an added
overload fails this case.

**The sideband half.** The four columns the receipt does NOT carry —
``validation_token``, ``session_id``, ``protocol``, ``webhook_secret`` — stay
explicit kwargs, defaulted to a preserve-if-not-passed sentinel. No single
registration surface knows all four: the A2A ``setTaskPushNotificationConfig``
handler passes ``validation_token``, admin registration passes
``webhook_secret`` (the RFC 9421 signing key), a transport passes its own
``protocol``, and each omits the rest. With a plain ``None`` default every one
of those writes would silently erase the other three on the reactivation
branch — for ``webhook_secret`` that means a working signed registration going
unsigned, with nothing failing. So: an omitted field keeps the existing row's
value, and an explicit ``None`` still clears.

Integration rather than unit because both claims are about COLUMNS: that the
value's three fields, and only the sidebands actually passed, are what a
subsequent read of the row returns. A mocked session would grade the calls, not
the writes.
"""

from __future__ import annotations

import inspect

import pytest

from src.core.database.models import Principal, PushNotificationConfig, Tenant
from src.core.database.repositories.push_notification_config import (
    PushNotificationConfigRepository,
)
from src.core.webhooks.registration import (
    ValidatedWebhookRegistration,
    accept_push_notification_config,
)
from tests.factories import PrincipalFactory, PushNotificationConfigFactory, TenantFactory
from tests.harness._base import BareIntegrationEnv

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

_TENANT_ID = "pncrepo_t1"
_PRINCIPAL_ID = "pncrepo_p1"

# A URL that clears the registration gate on its own merits (public host, https)
# — the case must fail because the SIGNATURE is wrong, never because the fixture
# URL needed a hatch the env did not open.
_WEBHOOK_URL = "https://buyer.example.com/adcp/webhook"

# The pinned AdCP 3.1.1 ``AuthenticationScheme`` spelling, which is what every
# writer in ``src/`` persists.
_HMAC_SCHEME = "HMAC-SHA256"
# >= 32 chars: the pinned schema (core/push-notification-config.json) sets
# authentication.credentials minLength 32, so a shorter fixture would be refused
# by the model before the case under test is reached.
_SECRET = "buyer-shared-secret-thirty-two-plus"

# The three parameters that must CEASE TO EXIST — the columns are written from
# the value's fields instead.
_RAW_STRING_PARAMS = ("url", "authentication_type", "authentication_token")

# The pre-existing row the sideband cases update. Its url and auth pair differ
# from the receipt's, so "the receipt REPLACED them" and "the sidebands survived"
# are distinguishable in one read-back.
_CONFIG_ID = "pnc_sideband_1"
_PREVIOUS_URL = "https://buyer.example.com/adcp/previously-registered"
_PREVIOUS_SCHEME = "Bearer"
_PREVIOUS_CREDENTIAL = "previous-bearer-credential-thirty-two"

# The four sideband values seeded on that row, one per sentinel-defaulted kwarg.
# ``_SIGNING_SECRET`` is the RFC 9421 HMAC key the sender signs with — distinct
# from ``_SECRET``, which is the buyer's credential carried BY the receipt.
_VALIDATION_TOKEN = "vtok"
_SESSION_ID = "sess-1"
_PROTOCOL = "a2a"
_SIGNING_SECRET = "s" * 32

_SIDEBANDS = (_VALIDATION_TOKEN, _SESSION_ID, _PROTOCOL, _SIGNING_SECRET)
_CLEARED = (None, None, None, None)


def _hmac_registration() -> ValidatedWebhookRegistration:
    """Build the value through the ONE public constructor buyers' configs go through."""
    return accept_push_notification_config(
        {
            "url": _WEBHOOK_URL,
            "authentication": {"schemes": [_HMAC_SCHEME], "credentials": _SECRET},
        }
    )


def _seeded_repo(env: BareIntegrationEnv) -> tuple[PushNotificationConfigRepository, Tenant, Principal]:
    """Create the tenant + principal the row's FKs require, return the repository.

    The tenant and principal come back because the sideband cases need them to
    seed a config row through ``PushNotificationConfigFactory``: passing
    ``tenant_id=`` alone would leave the factory's ``SubFactory`` free to insert
    a second, unrelated tenant that the row does not belong to.
    """
    tenant = TenantFactory(tenant_id=_TENANT_ID)
    principal = PrincipalFactory(tenant=tenant, principal_id=_PRINCIPAL_ID)
    return PushNotificationConfigRepository(env.get_session(), _TENANT_ID), tenant, principal


def _config_with_every_sideband(tenant: Tenant, principal: Principal) -> PushNotificationConfig:
    """An existing row with ALL FOUR sideband columns populated.

    All four, not just the one under test: a sentinel bug is per-column, and a
    fixture that leaves three of them NULL cannot tell "preserved" apart from
    "was already None".
    """
    return PushNotificationConfigFactory(
        tenant=tenant,
        principal=principal,
        id=_CONFIG_ID,
        url=_PREVIOUS_URL,
        authentication_type=_PREVIOUS_SCHEME,
        authentication_token=_PREVIOUS_CREDENTIAL,
        validation_token=_VALIDATION_TOKEN,
        session_id=_SESSION_ID,
        protocol=_PROTOCOL,
        webhook_secret=_SIGNING_SECRET,
    )


def _reloaded(env: BareIntegrationEnv, config_id: str) -> PushNotificationConfig:
    """Re-read the row FROM THE DATABASE rather than from the identity map.

    ``upsert`` mutates the very instances this session already holds, so a plain
    read-back would assert against the in-memory objects the method just
    assigned to, and would pass even if nothing were flushed. Expiring first
    forces the SELECT.
    """
    env.get_session().expire_all()
    row = env.get_one(PushNotificationConfig, tenant_id=_TENANT_ID, id=config_id)
    assert row is not None, f"upsert reported a write that produced no row with id {config_id!r}"
    return row


def _sidebands_of(row: PushNotificationConfig) -> tuple[str | None, str | None, str | None, str | None]:
    """The four sentinel-defaulted columns, read in the order ``upsert`` declares them."""
    return (row.validation_token, row.session_id, row.protocol, row.webhook_secret)


class TestUpsertTakesTheValue:
    """``upsert(registration, ...)`` — the receipt, not three strings."""

    def test_signature_takes_the_value_and_exposes_no_raw_string_upsert(self):
        """The leading parameter is the value; the three string parameters are gone.

        ``eval_str=True`` resolves the module's ``from __future__ import
        annotations`` strings to the real class, so the case grades the TYPE the
        repository declares rather than the spelling of a name.
        """
        signature = inspect.signature(PushNotificationConfigRepository.upsert, eval_str=True)
        parameters = [param for name, param in signature.parameters.items() if name != "self"]

        assert parameters[0].annotation is ValidatedWebhookRegistration, (
            f"upsert's leading parameter is {parameters[0].name}: "
            f"{parameters[0].annotation!r} — persistence still accepts something "
            f"other than the gate's receipt"
        )
        assert parameters[0].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD, (
            f"the registration is {parameters[0].kind.description}; callers must be "
            f"able to hand the value over positionally, as the lane's call sites do"
        )

        leftover = [name for name in _RAW_STRING_PARAMS if name in signature.parameters]
        assert leftover == [], (
            f"upsert still accepts {leftover} as loose strings — a value-taking "
            f"overload ADDED BESIDE the raw-string signature leaves every "
            f"unreceipted call site type-checking exactly as it does today"
        )

    def test_upsert_writes_the_values_fields_into_the_columns(self, integration_db):
        """The persisted row's three columns equal the value's three fields."""
        with BareIntegrationEnv(tenant_id=_TENANT_ID, principal_id=_PRINCIPAL_ID) as env:
            repo, _tenant, _principal = _seeded_repo(env)
            registration = _hmac_registration()

            config, created = repo.upsert(
                registration,
                config_id="pnc_value_1",
                principal_id=_PRINCIPAL_ID,
            )

            assert created is True
            stored = _reloaded(env, "pnc_value_1")
            assert stored.url == registration.url
            assert stored.authentication_type == registration.authentication_type
            assert stored.authentication_token == registration.authentication_token
            assert config.id == stored.id


class TestUpsertSidebandColumns:
    """The four kwargs the receipt does not carry are preserve-if-not-passed."""

    def test_upsert_preserves_sidebands_it_was_not_passed(self, integration_db):
        """An omitted ``webhook_secret`` does NOT clear the live signing key.

        The update arrives from a surface that knows only the registration — the
        shape create-media-buy and the admin re-registration path both have. It
        must rewrite the receipt's three columns and leave the four sidebands
        exactly as they were; a plain ``None`` default here would silently
        unsign a working RFC 9421 registration, with nothing failing.
        """
        with BareIntegrationEnv(tenant_id=_TENANT_ID, principal_id=_PRINCIPAL_ID) as env:
            repo, tenant, principal = _seeded_repo(env)
            _config_with_every_sideband(tenant, principal)

            _, created = repo.upsert(
                _hmac_registration(),
                config_id=_CONFIG_ID,
                principal_id=_PRINCIPAL_ID,
            )

            assert created is False
            stored = _reloaded(env, _CONFIG_ID)
            assert (stored.url, stored.authentication_type, stored.authentication_token) == (
                _WEBHOOK_URL,
                _HMAC_SCHEME,
                _SECRET,
            ), "the receipt's fields did not replace the row's previously-registered url/auth pair"
            assert _sidebands_of(stored) == _SIDEBANDS, (
                "an omitted sideband was erased — a registration-only update must not "
                "clear the validation token, session, protocol or signing secret"
            )

    def test_upsert_explicit_none_still_clears_a_sideband(self, integration_db):
        """Passing ``None`` explicitly is a real clear, not a no-op.

        The other half of the sentinel: preserve-if-not-passed must not become
        preserve-always, or a caller could never retire a rotated signing secret
        or a stale validation token.
        """
        with BareIntegrationEnv(tenant_id=_TENANT_ID, principal_id=_PRINCIPAL_ID) as env:
            repo, tenant, principal = _seeded_repo(env)
            _config_with_every_sideband(tenant, principal)

            repo.upsert(
                _hmac_registration(),
                config_id=_CONFIG_ID,
                principal_id=_PRINCIPAL_ID,
                validation_token=None,
                session_id=None,
                protocol=None,
                webhook_secret=None,
            )

            stored = _reloaded(env, _CONFIG_ID)
            assert _sidebands_of(stored) == _CLEARED, "an explicitly-passed None was swallowed by the preserve branch"

    def test_upsert_insert_defaults_unpassed_sidebands_to_none(self, integration_db):
        """On INSERT the sentinel means NULL — never the sentinel object itself.

        The insert branch resolves each sentinel separately from the update
        branch, so it needs its own case: leaking ``_UNSET`` into the column
        would fail at flush, and defaulting it to anything but NULL would invent
        a signing secret nobody registered.
        """
        with BareIntegrationEnv(tenant_id=_TENANT_ID, principal_id=_PRINCIPAL_ID) as env:
            repo, _tenant, _principal = _seeded_repo(env)

            config, created = repo.upsert(
                _hmac_registration(),
                config_id="pnc_fresh",
                principal_id=_PRINCIPAL_ID,
            )

            assert created is True
            stored = _reloaded(env, config.id)
            assert _sidebands_of(stored) == _CLEARED
            assert stored.is_active is True
