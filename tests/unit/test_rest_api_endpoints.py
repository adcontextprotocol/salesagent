"""Tests for REST API /api/v1/* endpoints (all handlers except get_products).

Validates that each REST transport endpoint:
- Route exists (not 404)
- Returns 200 with valid mock data
- Auth-optional endpoints work without auth

"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from adcp.types import AccountReference as LibraryAccountReference
from adcp.types import ContextObject, ExtensionObject, PushNotificationConfig, ReportingWebhook
from starlette.testclient import TestClient

from src.app import app
from src.core.resolved_identity import ResolvedIdentity
from tests.helpers import assert_envelope_shape

client = TestClient(app)

_MOCK_IDENTITY = ResolvedIdentity(
    principal_id="test-principal",
    tenant_id="default",
    tenant={"tenant_id": "default"},
    auth_token="test-token",
    protocol="rest",
)


# ---------------------------------------------------------------------------
# Discovery endpoints (auth-optional)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Auth-required endpoints
# ---------------------------------------------------------------------------


class TestCreateMediaBuyEndpoint:
    """Verify POST /api/v1/media-buys endpoint."""

    def test_requires_auth(self):
        """create_media_buy requires authentication."""
        response = client.post(
            "/api/v1/media-buys",
            json={"packages": []},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Runtime scalar-forwarding oracles (#1417)
#
# The body-completeness guard proves each REST scalar is DECLARED on the *_raw
# wrapper signature; it does NOT prove the route actually forwards the request
# value. These TestClient tests patch the *_raw wrapper and assert the sentinel
# value the buyer sent reaches the wrapper — one test per non-echoed scalar.
# ---------------------------------------------------------------------------

# field -> (wire value, value the route must forward to the raw wrapper).
# Object params are coerced to typed models at the route (#1417), so the
# forwarded value is the model, not the wire dict; ext stays a raw dict.
# push_notification_config coerces to the PINNED type: ingest is spec-exact, so a
# non-spec scheme or casing is refused here. The widened LibraryAuthentication
# applies only when REHYDRATING an already-stored row (see registration.from_stash).
_CREATE_WEBHOOK_WIRE = {
    "url": "https://example.com/hook",
    "authentication": {"schemes": ["Bearer"], "credentials": "e9kw-credential-value-of-32-chars"},
    "reporting_frequency": "daily",
}
_CREATE_PNC_WIRE = {"url": "https://example.com/push"}
_CREATE_CONTEXT_WIRE = {"conversation_id": "conv-e9kw"}
_CREATE_FORWARDED_SCALARS = {
    "reporting_webhook": (_CREATE_WEBHOOK_WIRE, ReportingWebhook.model_validate(_CREATE_WEBHOOK_WIRE)),
    "push_notification_config": (_CREATE_PNC_WIRE, PushNotificationConfig.model_validate(_CREATE_PNC_WIRE)),
    "context": (_CREATE_CONTEXT_WIRE, ContextObject.model_validate(_CREATE_CONTEXT_WIRE)),
    # Coerced, like ``context`` above: the REST body is DERIVED from the DTO now, so ``ext``
    # arrives as the DTO's ExtensionObject rather than a bare dict. That is the DTO's type
    # reaching the wrapper, which is the point of deriving.
    "ext": (
        {"e9kw_marker": "create-value"},
        ExtensionObject.model_validate({"e9kw_marker": "create-value"}),
    ),
}

_UPDATE_FORWARDED_SCALARS = {
    "pacing": "even",
    "daily_budget": 1234.5,
}


class TestCreateMediaBuyScalarForwarding:
    """Each non-echoed create scalar reaches create_media_buy_raw at runtime."""

    @pytest.mark.parametrize(
        ("field", "wire_value", "expected"),
        [(f, w, e) for f, (w, e) in _CREATE_FORWARDED_SCALARS.items()],
        ids=list(_CREATE_FORWARDED_SCALARS),
    )
    @patch("src.core.resolved_identity.resolve_identity", return_value=_MOCK_IDENTITY)
    @patch("src.core.tools.media_buy_create.create_media_buy_raw", new_callable=AsyncMock)
    def test_scalar_forwards_to_raw(self, mock_raw, mock_resolve, field, wire_value, expected):
        mock_raw.return_value = MagicMock(model_dump=lambda **kw: {})
        body = {
            # A BUILDABLE payload: create-media-buy-request.json puts minItems 1 on
            # packages. An empty list passed only while create_media_buy_raw was mocked --
            # mocking it also mocked away the builder inside it, so nothing validated the
            # body. The route builds before calling now, so the payload must be one a
            # buyer could actually send.
            "packages": [{"product_id": "prod_1", "budget": 5000.0, "pricing_option_id": "po_1"}],
            "start_time": "2026-01-01T00:00:00Z",
            "end_time": "2026-02-01T00:00:00Z",
            # create-media-buy-request.json /required. The body is DERIVED from the DTO now,
            # so requiredness is enforced at the REST edge as it already was on mcp and a2a
            # -- a payload missing these is not a valid request on any transport.
            "idempotency_key": "rest-create-key-000001",
            "brand": {"domain": "example.com"},
            "account": {"account_id": "acct_rest_test"},
            field: wire_value,
        }
        response = client.post("/api/v1/media-buys", json=body, headers={"Authorization": "Bearer test-token"})

        assert response.status_code == 200, response.text
        # Each scalar is graded on the built REQUEST the wrapper receives -- except
        # push_notification_config, which stays a kwarg beside it (gh-#1299).
        kwargs = mock_raw.call_args.kwargs
        actual = kwargs[field] if field in kwargs else getattr(kwargs["req"], field)
        assert actual == expected, f"REST create route did not forward {field!r} to create_media_buy_raw"


class TestGetMediaBuyDeliveryEndpoint:
    """Verify POST /api/v1/media-buys/delivery endpoint."""

    @patch("src.core.resolved_identity.resolve_identity", return_value=_MOCK_IDENTITY)
    @patch("src.core.transport_helpers.enrich_identity_with_account")
    @patch("src.core.tools.media_buy_delivery._get_media_buy_delivery_impl")
    def test_account_is_coerced_before_enriching_identity(self, mock_impl, mock_enrich, mock_resolve):
        # Patches _impl, NOT get_media_buy_delivery_raw: enrichment lives in the raw
        # wrapper now (one site, off req.account, instead of a copy per transport), so
        # mocking the wrapper out would make mock_enrich unreachable and the test vacuous.
        enriched_identity = _MOCK_IDENTITY.model_copy(update={"account_id": "acct-1"})
        mock_enrich.return_value = enriched_identity
        mock_impl.return_value = MagicMock(model_dump=lambda **kw: {"media_buys": []})

        response = client.post(
            "/api/v1/media-buys/delivery",
            json={
                "media_buy_ids": ["mb1"],
                "account": {"brand": {"domain": "example.com"}, "operator": "op-1", "sandbox": False},
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        expected_account = LibraryAccountReference.model_validate(
            {"brand": {"domain": "example.com"}, "operator": "op-1", "sandbox": False}
        )
        # The COERCED, typed AccountReference is what reaches enrichment -- the raw dict
        # is what used to crash resolve_account on ``account_ref.root``.
        mock_enrich.assert_called_once_with(_MOCK_IDENTITY, expected_account)
        # And it rides on the request, so every transport carries it the one way.
        assert mock_impl.call_args[0][0].account == expected_account
        assert mock_impl.call_args[0][1] is enriched_identity

    @patch("src.core.resolved_identity.resolve_identity", return_value=_MOCK_IDENTITY)
    @patch("src.core.transport_helpers.enrich_identity_with_account")
    @patch("src.core.tools.media_buy_delivery.get_media_buy_delivery_raw")
    def test_malformed_account_returns_validation_error(self, mock_impl, mock_enrich, mock_resolve):
        response = client.post(
            "/api/v1/media-buys/delivery",
            json={"media_buy_ids": ["mb1"], "account": {}},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 400
        assert_envelope_shape(response.json(), "INVALID_REQUEST", recovery="correctable")
        mock_enrich.assert_not_called()
        mock_impl.assert_not_called()


class TestPathFieldsBindFromTheUrl:
    """A templated REST path fills the DTO field it names.

    ``RestBinding.path_fields`` used to be read nowhere: the URL template carried the
    convertor, Starlette parsed the segment, and the handler's signature was ``(body,
    identity)``, so the value was discarded. A buyer who named the task in the URL -- the
    only place REST puts it -- got a 422 for omitting it from the body, and a buyer who sent
    both got the BODY's value while the URL said something else.
    """

    @patch("src.core.resolved_identity.resolve_identity", return_value=_MOCK_IDENTITY)
    @patch("src.core.tools.task_management._get_task_impl")
    def test_path_value_reaches_the_impl_without_a_body_field(self, mock_impl, mock_resolve):
        mock_impl.return_value = MagicMock(model_dump=lambda **kw: {"task": {}})

        response = client.post(
            "/api/v1/tasks/task_from_url",
            json={},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        assert mock_impl.call_args.kwargs["req"].task_id == "task_from_url"

    @patch("src.core.resolved_identity.resolve_identity", return_value=_MOCK_IDENTITY)
    @patch("src.core.tools.task_management._get_task_impl")
    def test_the_url_wins_over_a_body_that_disagrees(self, mock_impl, mock_resolve):
        """The URL is the resource identity, so it overrides a conflicting body value."""
        mock_impl.return_value = MagicMock(model_dump=lambda **kw: {"task": {}})

        response = client.post(
            "/api/v1/tasks/task_from_url",
            json={"task_id": "task_from_body"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        assert mock_impl.call_args.kwargs["req"].task_id == "task_from_url"
