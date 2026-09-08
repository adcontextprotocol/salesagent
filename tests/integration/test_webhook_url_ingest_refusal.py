"""Ingest-time egress refusal of buyer-supplied webhook URLs, on the wire.

A buyer-supplied ``push_notification_config.url`` / ``reporting_webhook.url``
is a URL we STORE now and FETCH later — an SSRF vector the egress seam
(``src/core/security/outbound_http.py``) refuses at delivery time. But the
buyer supplied it at ingest, on a request/response cycle where a correctable
refusal is still possible. Accepting the URL with a 'success' and failing the
delivery silently later gives the buyer no channel to learn the URL is wrong
(GH #1697; the same obligation GH #1589 implemented for
``property_list.agent_url``, the other buyer-supplied URL on the protocol
surface — exemplar: ``tests/integration/test_property_list_resolver.py``
``TestRefusedBuyerUrlOnTheWire``).

What this pins, per ingest surface (create_media_buy, update_media_buy,
sync_creatives) with both egress escape hatches CLOSED:

* the request FAILS at ingest (no 'success' followed by a silent delivery
  failure), and
* the wire envelope is ``VALIDATION_ERROR`` / ``correctable`` with
  ``error.field`` naming exactly which buyer input to fix and a buyer-facing
  ``suggestion`` telling them what an acceptable URL looks like — all graded on
  BOTH envelope layers. Every surface refuses through the one registration-time
  SSRF gate (``reject_unsafe_webhook_registration_url``, which raises
  ``AdCPValidationError``); see ``_REGISTRATION_GATE_CODE`` below, and
* the refused config leaves NO side effect (no persisted
  push_notification_config row; no creative synced) — the refusal happens
  BEFORE the storage points, not per-item inside them.

Spec grounding — AdCP 3.1.1, the version this repo PINS (``adcp==6.6.0``,
``docs/adcp-spec-version.md``; prose via ``git -C <adcp-checkout> show
v3.1.1:<path>``):

1. ``docs/building/by-layer/L1/security.mdx`` § "Webhook URL validation
   (SSRF)": "Any URL that a buyer, seller, or governance agent provides for
   another party to fetch is an SSRF vector." Points 1 (reject non-HTTPS) and
   2 (reject reserved-range addresses; 169.254.169.254 named outright)
   prescribe the refusal; point 6 prescribes the silence about our network —
   which leaves ``error.field`` as the only channel naming WHICH input to fix.
2. ``docs/building/by-layer/L3/error-handling.mdx`` § "Request Validation"
   (``VALIDATION_ERROR | correctable``) + § "Recovery Classification": a URL
   egress policy refuses identically forever, so ``transient`` would promise
   something false. ``VALIDATION_ERROR`` is the code the registration gate
   emits, and it is independently pinned for the sync_creatives leg by
   ``tests/bdd/features/BR-UC-006-sync-creatives.feature``
   ``@T-UC-006-ext-webhook-ssrf`` (``VALIDATION_ERROR`` + ``correctable`` +
   ``suggestion``, carrying an ``@source repo=adcp ref=v3.1.1`` citation on
   ``dist/schemas/3.1.1/enums/error-code.json``).
3. ``push_notification_config`` is a TOP-LEVEL property of
   ``dist/schemas/3.1.1/media-buy/create-media-buy-request.json`` (``$ref``
   ``core/push-notification-config.json``, required ``["url"]``); same
   top-level shape in ``update-media-buy-request.json`` and
   ``creative/sync-creatives-request.json``; ``reporting_webhook`` likewise
   top-level on create/update. Hence the field paths are
   ``push_notification_config.url`` / ``reporting_webhook.url``.

Conformance storyboard: UNGRADED — nothing in ``dist/compliance/3.1.1/``
grades a seller refusing a counterparty-supplied URL (same finding recorded
for GH #1589).

No acceptance-path twin lives here on purpose: the ~38 existing suites that
pass ``push_notification_config`` fixtures through these same surfaces are the
acceptance coverage, and migrating their hatch-immune NXDOMAIN fixture hosts
is budgeted as its own step of the GH #1697 plan (step 0) — grading
acceptance here against a resolvable host would re-decide that fixture policy
in a second place.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from tests.harness.media_buy_create import MediaBuyCreateEnv
from tests.harness.media_buy_dual import MediaBuyDualEnv
from tests.harness.transport import Transport
from tests.helpers import assert_envelope_shape
from tests.helpers.adcp_factories import create_test_media_buy_request_dict
from tests.integration.property_list_helpers import enforce_egress_policy

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

# Wire transports that carry these fields on create/update. All three declare
# and forward push_notification_config (MCP wrapper media_buy_create.py:4392 /
# A2A skill / REST CreateMediaBuyBody), so a transport that cannot refuse it
# is a protocol gap, not a transport quirk.
_WIRE_TRANSPORTS = [Transport.MCP, Transport.A2A, Transport.REST]

# All wire transports carry reporting_webhook on update — the A2A skill's
# forwarding gap (it silently dropped the field) was closed in the same change
# that added the ingest validation, so its leg grades both the forwarding and
# the refusal.
_UPDATE_REPORTING_WEBHOOK_TRANSPORTS = [Transport.MCP, Transport.A2A, Transport.REST]

# Buyer-supplied URLs the seam refuses before opening a connection: one for
# scheme policy, one for address policy. Neither resolves DNS or touches the
# network, so both are hermetic (nbbe exemplar).
#
# The five ``192.x``/``2001:20::/28`` rows are the reserved ranges carried
# verbatim from adcontextprotocol/adcp-client-python#974 into
# ``egress.policy._SUPPLEMENT_NETWORKS`` rather than by bumping to adcp 7.x
# (owner decision, GH #1792 — that bump is a major version jump
# carrying far more than this SSRF fix). ``cgnat-metadata-address`` is the one
# address the spike actually found leaking (Alibaba Cloud's metadata service at
# 100.100.100.200, inside the CGNAT block) — it is graded on its own row,
# distinct from the generic ``cgnat-range`` row, because it is the specific
# gap that motivated re-scoping this ticket.
_REFUSED_WEBHOOK_URLS = [
    pytest.param("http://buyer-callback.example.com/hook", id="non-https-scheme"),
    pytest.param("https://169.254.169.254/hook", id="cloud-metadata-address"),
    pytest.param("https://100.64.0.1/hook", id="cgnat-range"),
    pytest.param("https://100.100.100.200/hook", id="cgnat-metadata-address"),
    pytest.param("https://192.88.99.1/hook", id="6to4-relay-anycast"),
    pytest.param("https://192.31.196.1/hook", id="as112-v4"),
    pytest.param("https://192.52.193.1/hook", id="amt"),
    pytest.param("https://192.175.48.1/hook", id="as112-direct"),
    pytest.param("https://[2001:20::1]/hook", id="orchidv2"),
]

# One representative refused URL for the surfaces where the two causes share
# the exact same seam call (both causes are graded per-transport on the
# headline create + push_notification_config matrix above).
_METADATA_URL = "https://169.254.169.254/hook"

# JSONPath-lite paths into the buyer's request document (written as literals,
# not derived — ``error.field`` is a fact about the buyer's document; see the
# nbbe exemplar's ``_REFUSED_FIELD_PATH`` rationale).
_PNC_FIELD = "push_notification_config.url"
_REPORTING_WEBHOOK_FIELD = "reporting_webhook.url"

# The wire code is a fact about WHICH gate refused, and all three ingest
# surfaces call the SAME one: the DNS-free registration gate
# (``src/core/webhook_validator.py`` ``reject_unsafe_webhook_registration_url``
# — create_media_buy media_buy_create.py:2060/2067 and the A2A create skill
# adcp_a2a_server.py:154, update_media_buy media_buy_update.py:393/406,
# sync_creatives _sync.py:114). It raises ``AdCPValidationError``:
# VALIDATION_ERROR / correctable / field / suggestion. Deliberately NOT the
# outbound seam's ``validate_url``, which always resolves DNS and would refuse a
# buyer whose hostname has not propagated yet — the seam stays the SEND-time
# gate (gh-#1589 / gh-#1697). Independently pinned for the sync leg by BR-UC-006
# ``@T-UC-006-ext-webhook-ssrf``.
_REGISTRATION_GATE_CODE = "VALIDATION_ERROR"

# A schema-valid ReportingWebhook carrying a refused URL: url/authentication/
# reporting_frequency are required by the pinned core/reporting-webhook.json,
# and Authentication.credentials has MinLen(32) — the request must be valid
# AS A DOCUMENT so the ONLY possible rejection is the egress refusal.
_REFUSED_REPORTING_WEBHOOK = {
    "url": _METADATA_URL,
    "reporting_frequency": "daily",
    "authentication": {"schemes": ["Bearer"], "credentials": "x" * 40},
}


def _assert_refused_at_ingest(result, field: str, surface: str, *, code: str) -> None:
    """The one refusal contract, graded on the wire envelope.

    ``result.error_envelope()`` is the one reader (tests/CLAUDE.md Error
    Verification Policy). It returns the real wire wherever one exists and the
    builder's envelope only on IMPL, which has no wire by definition — so the
    call site no longer chooses between them, and cannot choose wrongly.

    ``code`` is the emitting gate's wire code (``_REGISTRATION_GATE_CODE``) —
    passed explicitly at every call site so a surface that starts refusing
    through some other gate cannot silently inherit this one's code.
    """
    assert result.is_error, (
        f"A refused buyer-supplied webhook URL must fail {surface} at ingest with a "
        f"correctable error — not be accepted into storage for a silent delivery "
        f"failure later. Got: {getattr(result, 'wire_response', None) or result.payload!r}"
    )
    envelope = result.error_envelope()
    assert_envelope_shape(
        envelope,
        code,
        recovery="correctable",
        field=field,
    )
    _assert_registration_suggestion(envelope, surface)


def _assert_registration_suggestion(envelope: dict, surface: str) -> None:
    """The registration gate's buyer-facing ``suggestion``, on BOTH envelope layers.

    ``reject_unsafe_webhook_registration_url`` passes
    ``suggestion=webhook_ssrf_suggestion()``, and
    ``build_two_layer_error_envelope`` (exceptions.py:1028-1043) copies
    ``errors[0]`` into ``adcp_error``, so both layers must carry it. Graded
    because spec point 6 keeps our network out of the message, which leaves
    ``field`` + ``suggestion`` as the buyer's only repair instructions — the
    same triple BR-UC-006 ``@T-UC-006-ext-webhook-ssrf`` grades. The expected
    text is read from production in-process so the strict/dev variant matches
    the posture the test actually ran under.
    """
    from src.core.webhook_validator import webhook_ssrf_suggestion

    expected = webhook_ssrf_suggestion()
    for layer, body in (("adcp_error", envelope["adcp_error"]), ("errors[0]", envelope["errors"][0])):
        assert body.get("suggestion") == expected, (
            f"{surface}: {layer}.suggestion={body.get('suggestion')!r}, expected {expected!r} — "
            f"a refusal that names no repair leaves the buyer nothing to act on"
        )


def _assert_no_push_config_persisted(tenant_id: str, principal_id: str) -> None:
    """The refused URL left no push_notification_configs row.

    The repository upsert is the single write funnel for this table
    (GH #1697 disposition row 19: the repository is the verification
    point, deliberately not the fix site), so an empty active list for the
    principal IS "the refusal preceded the store".
    """
    from src.core.database.repositories.uow import PushNotificationConfigUoW

    with PushNotificationConfigUoW(tenant_id) as uow:
        assert uow.push_notification_configs is not None
        persisted = uow.push_notification_configs.list_active_by_principal(principal_id)
    assert persisted == [], (
        f"a refused push_notification_config.url must not be persisted, found {[(c.id, c.url) for c in persisted]}"
    )


def _create_kwargs(product) -> dict:
    """A fully valid create_media_buy request (real product/pricing chain).

    Everything except the webhook config under test comes from the shared
    builder, so the refusal — not a package/pricing rejection — is the only
    possible error. ``brand.domain`` and ``po_number`` are this file's own
    labels and stay explicit; the dates and the idempotency key are not this
    file's business and come from the factory's defaults.
    """
    return create_test_media_buy_request_dict(
        product_ids=[product.product_id],
        pricing_option_id="cpm_usd_fixed",
        total_budget=5000.0,
        brand={"domain": "webhook-ingest.example.com"},
        po_number=f"WEBHOOK-INGEST-{uuid.uuid4().hex[:8]}",
    )


class TestCreateMediaBuyRefusedPushNotificationConfigUrl:
    """create_media_buy refuses a policy-refused push_notification_config.url at ingest.

    Today _create_media_buy_impl (media_buy_create.py:2120/2135) stores the
    config into workflow_metadata AND persists a DBPushNotificationConfig row
    with zero validation, and the create returns success — the buyer learns
    nothing until a delivery silently fails.
    """

    @pytest.mark.parametrize("transport", _WIRE_TRANSPORTS, ids=lambda t: t.value)
    @pytest.mark.parametrize("url", _REFUSED_WEBHOOK_URLS)
    def test_refused_url_fails_create_naming_the_field(self, integration_db, transport, url, monkeypatch):
        """VALIDATION_ERROR / correctable / field=push_notification_config.url, and no row persisted."""
        enforce_egress_policy(monkeypatch)

        with MediaBuyCreateEnv() as env:
            _tenant, _principal, product, _pricing = env.setup_media_buy_data()

            result = env.call_via(
                transport,
                push_notification_config={"url": url},
                **_create_kwargs(product),
            )

            _assert_refused_at_ingest(result, _PNC_FIELD, surface="create_media_buy", code=_REGISTRATION_GATE_CODE)
            _assert_no_push_config_persisted(env._tenant_id, env._principal_id)

    def test_cgnat_metadata_address_stays_refused_under_allow_private(self, integration_db, monkeypatch):
        """100.100.100.200 (Alibaba Cloud metadata, inside the CGNAT block) is refused
        even with ADCP_OUTBOUND_ALLOW_PRIVATE=true.

        This is the address the original spike actually found leaking (GH #1792):
        the registration gate (``src/core/security/egress/policy.py``
        ``_SUPPLEMENT_NETWORKS``, read via ``EgressPolicy.check_registration``)
        never reads that hatch at all — it is a SEND-time seam knob — so this pins that
        fact rather than the seam's own metadata-outranks-the-override behaviour, which
        is graded separately in ``tests/integration/test_outbound_http.py``.
        """
        from tests.integration.test_outbound_http import set_flags

        set_flags(monkeypatch, private=True)

        with MediaBuyCreateEnv() as env:
            _tenant, _principal, product, _pricing = env.setup_media_buy_data()

            result = env.call_via(
                Transport.MCP,
                push_notification_config={"url": "https://100.100.100.200/hook"},
                **_create_kwargs(product),
            )

            _assert_refused_at_ingest(result, _PNC_FIELD, surface="create_media_buy", code=_REGISTRATION_GATE_CODE)
            _assert_no_push_config_persisted(env._tenant_id, env._principal_id)


class TestCreateMediaBuyRefusedReportingWebhookUrl:
    """create_media_buy refuses a policy-refused reporting_webhook.url at ingest.

    Same choke point, second buyer-supplied URL on the create request: today
    the impl only warns about a non-daily frequency (media_buy_create.py:2034)
    and persists the webhook inside raw_request, where the nightly
    delivery_webhook_scheduler reads it back with no request left to refuse
    into (GH #1697 disposition row 7).
    """

    @pytest.mark.parametrize("transport", _WIRE_TRANSPORTS, ids=lambda t: t.value)
    def test_refused_url_fails_create_naming_the_field(self, integration_db, transport, monkeypatch):
        """VALIDATION_ERROR / correctable / field=reporting_webhook.url on the create wire."""
        enforce_egress_policy(monkeypatch)

        with MediaBuyCreateEnv() as env:
            _tenant, _principal, product, _pricing = env.setup_media_buy_data()

            result = env.call_via(
                transport,
                reporting_webhook=dict(_REFUSED_REPORTING_WEBHOOK),
                **_create_kwargs(product),
            )

            _assert_refused_at_ingest(
                result, _REPORTING_WEBHOOK_FIELD, surface="create_media_buy", code=_REGISTRATION_GATE_CODE
            )


class TestUpdateMediaBuyRefusedWebhookUrls:
    """update_media_buy refuses policy-refused webhook URLs at ingest.

    The update path stores push_notification_config / reporting_webhook inside
    the workflow step's request_data (media_buy_update.py:1487-1492 →
    request_data=req), which context_manager.py:836 later reads back and
    dials. Today the update accepts the refused URL and returns success. The
    refusal must sit ABOVE the UoW/state machine: a refused URL is a property
    of the request as sent, so it outranks any INVALID_STATE question
    (GH #1697 plan step 4) — these tests use an active buy so no state
    refusal can mask a vacuous pass either way.
    """

    @pytest.fixture
    def env_with_media_buy(self, integration_db):
        from tests.factories import MediaBuyFactory, MediaPackageFactory

        with MediaBuyDualEnv() as env:
            tenant, principal, product, _ = env.setup_media_buy_data()
            mb = MediaBuyFactory(
                tenant=tenant,
                principal=principal,
                status="active",
                currency="USD",
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC) + timedelta(days=30),
            )
            MediaPackageFactory(
                media_buy=mb,
                package_config={"package_id": "pkg_001", "product_id": product.product_id, "budget": 5000.0},
            )
            env._commit_factory_data()
            env._seeded_media_buy_id = mb.media_buy_id
            yield env, mb

    def _update_req(self, media_buy, **webhook_kwargs):
        """An otherwise-valid update (budget change) carrying a refused webhook URL."""
        from src.core.schemas import UpdateMediaBuyRequest

        return UpdateMediaBuyRequest(media_buy_id=media_buy.media_buy_id, budget=9999.0, **webhook_kwargs)

    @pytest.mark.parametrize("transport", _WIRE_TRANSPORTS, ids=lambda t: t.value)
    def test_refused_push_notification_config_url_fails_update(self, env_with_media_buy, transport, monkeypatch):
        """VALIDATION_ERROR / correctable / field=push_notification_config.url on the update wire."""
        enforce_egress_policy(monkeypatch)
        env, media_buy = env_with_media_buy

        req = self._update_req(media_buy, push_notification_config={"url": _METADATA_URL})
        result = env.call_via(transport, req=req)

        _assert_refused_at_ingest(result, _PNC_FIELD, surface="update_media_buy", code=_REGISTRATION_GATE_CODE)

    @pytest.mark.parametrize("transport", _UPDATE_REPORTING_WEBHOOK_TRANSPORTS, ids=lambda t: t.value)
    def test_refused_reporting_webhook_url_fails_update(self, env_with_media_buy, transport, monkeypatch):
        """VALIDATION_ERROR / correctable / field=reporting_webhook.url on the update wire."""
        enforce_egress_policy(monkeypatch)
        env, media_buy = env_with_media_buy

        req = self._update_req(media_buy, reporting_webhook=dict(_REFUSED_REPORTING_WEBHOOK))
        result = env.call_via(transport, req=req)

        _assert_refused_at_ingest(
            result, _REPORTING_WEBHOOK_FIELD, surface="update_media_buy", code=_REGISTRATION_GATE_CODE
        )


class TestSyncCreativesRefusedPushNotificationConfigUrl:
    """sync_creatives refuses a policy-refused push_notification_config.url at ingest.

    Third protocol ingest of the same field: _sync.py:111-118 extracts the
    webhook URL for AI-review callbacks and _workflow.py stores the config in
    workflow request_data. Today the sync accepts it and returns success.

    The refusal must be REQUEST-level, not laundered into a per-creative
    failure: inside the per-creative try (_sync.py:150) or _processing.py's
    ``except Exception`` it would surface as a partial success with a
    transient per-item error ("retry recommended" — false forever). The
    request-level VALIDATION_ERROR/correctable/field/suggestion asserts pin exactly that
    (a laundered refusal is a success envelope, or transient recovery — both
    fail here), and the no-creative-persisted assert pins that the refusal
    precedes per-creative processing entirely (plan step 5).
    """

    # IMPL included alongside the wire transports: the laundering hazard lives
    # in _impl/_processing, observable on every dispatch path. Same transport
    # matrix as the sibling sync error tests (test_creative_sync_transport.py).
    _ALL_TRANSPORTS = [Transport.IMPL, Transport.A2A, Transport.REST, Transport.MCP]

    @pytest.mark.parametrize("transport", _ALL_TRANSPORTS, ids=lambda t: t.value)
    def test_refused_url_fails_sync_naming_the_field(self, integration_db, transport, monkeypatch):
        """VALIDATION_ERROR / correctable / field=push_notification_config.url; nothing synced."""
        from tests.factories.creative_asset import CreativeAssetFactory
        from tests.harness import CreativeSyncEnv

        enforce_egress_policy(monkeypatch)
        creative_id = f"c_refused_pnc_{uuid.uuid4().hex[:8]}"

        with CreativeSyncEnv() as env:
            env.setup_default_data()

            creative = CreativeAssetFactory(creative_id=creative_id, name="Refused PNC Creative")
            result = env.call_via(
                transport,
                creatives=[creative],
                push_notification_config={"url": _METADATA_URL},
            )

            _assert_refused_at_ingest(result, _PNC_FIELD, surface="sync_creatives", code=_REGISTRATION_GATE_CODE)

            # The refusal precedes per-creative processing: a refused request
            # syncs NOTHING (placement outside the per-creative try, plan step 5).
            from src.core.database.repositories.uow import CreativeUoW

            with CreativeUoW(env._tenant_id) as uow:
                assert uow.creatives is not None
                persisted = uow.creatives.get_by_ids([creative_id], env._principal_id)
            assert persisted == [], (
                f"a sync refused for its push_notification_config.url must apply no "
                f"creative writes, found {[c.creative_id for c in persisted]}"
            )
