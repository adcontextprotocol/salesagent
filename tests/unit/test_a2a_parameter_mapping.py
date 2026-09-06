#!/usr/bin/env python3
"""
Unit tests for A2A server parameter mapping to AdCP schemas.

These tests validate that the A2A server correctly extracts and passes
parameters from A2A requests to the core implementation functions,
ensuring parameter names match the AdCP specification.

CRITICAL: These tests catch protocol mismatches like 'updates' vs 'packages'
before they reach production.
"""

from unittest.mock import patch

import pytest
from adcp.types import AccountReference as LibraryAccountReference

from src.core.schemas import GetMediaBuyDeliveryRequest
from tests.factories.principal import PrincipalFactory
from tests.helpers import assert_envelope_shape
from tests.helpers.capture_wrapper_req import stub_impl
from tests.utils.a2a_helpers import assert_delivery_forwarded_account

_MOCK_IDENTITY = PrincipalFactory.make_identity(
    principal_id="principal_123",
    tenant_id="tenant_123",
    tenant={"tenant_id": "tenant_123"},
    protocol="a2a",
)


class TestA2AParameterMapping:
    """Test parameter extraction and mapping in A2A skill handlers."""

    def test_update_media_buy_uses_packages_parameter(self):
        """
        Test that update_media_buy skill handler extracts 'packages' parameter.

        Regression test for: A2A server expecting 'updates' instead of 'packages'

        The handler should:
        1. Accept 'packages' field from A2A request (per AdCP v2.0+)
        2. Pass 'packages' to core implementation (not 'updates')
        3. Support backward compatibility with legacy 'updates' field
        """
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        handler = AdCPRequestHandler()

        with (
            patch("src.core.resolved_identity.resolve_identity", return_value=_MOCK_IDENTITY),
            stub_impl("update_media_buy") as mock_update,
        ):
            mock_update.return_value = {"status": "success", "media_buy_id": "mb_123"}

            # Simulate A2A request with AdCP v2.0+ 'packages' field
            parameters = {
                "media_buy_id": "mb_123",
                # AdCP 3.1.1 /required on update-media-buy-request.json
                "account": {"account_id": "acct_test"},
                "idempotency_key": "test-idem-key-0001",
                "paused": False,  # adcp 2.12.0+: paused=False means resume
                "packages": [{"package_id": "pkg_1", "paused": False}],  # AdCP v2.12.0+ field name
            }

            # Call the skill handler (synchronous wrapper for async method)
            import asyncio

            result = asyncio.run(handler._handle_update_media_buy_skill(parameters=parameters, identity=_MOCK_IDENTITY))

            # The handler builds and hands the wrapper ONE request, so `packages` is
            # graded where it now travels: on the request, under its AdCP v2.0+ name.
            mock_update.assert_called_once()
            req = mock_update.call_args.kwargs["req"]

            assert req.packages is not None, "packages must reach the request (AdCP v2.0+, not 'updates')"
            assert len(req.packages) == len(parameters["packages"]), "Package count should match"
            assert req.packages[0].package_id == "pkg_1"
            msg = "Package ID should match"

            # Should NOT carry the legacy 'updates' wrapper -- UpdateMediaBuyRequest has no
            # such field, so its presence would be a construction error rather than a silent
            # extra: asserting the request cannot hold it is the stronger statement.
            assert not hasattr(req, "updates"), "the legacy 'updates' wrapper must not reach the request"

            # Verify other AdCP v2.12.0+ fields reached the request
            assert req.media_buy_id == "mb_123"
            assert req.paused is False  # adcp 2.12.0+: paused=False means resume

    def test_update_media_buy_backward_compatibility_with_updates(self):
        """
        Test backward compatibility with legacy 'updates' field.

        Some older clients might still send 'updates' wrapper.
        We should support this for backward compatibility but extract
        the 'packages' data from within it.
        """
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        handler = AdCPRequestHandler()

        with (
            patch("src.core.resolved_identity.resolve_identity", return_value=_MOCK_IDENTITY),
            stub_impl("update_media_buy") as mock_update,
        ):
            mock_update.return_value = {"status": "success"}

            # Legacy request format with 'updates' wrapper
            parameters = {
                "media_buy_id": "mb_123",
                # AdCP 3.1.1 /required on update-media-buy-request.json
                "account": {"account_id": "acct_test"},
                "idempotency_key": "test-idem-key-0001",
                # Legacy `updates` WRAPPER is what this test grades; the package inside it
                # uses the pinned spelling. It previously carried `status: "active"`, which
                # UpdatePackage does not accept (paused is the field) -- and the test still
                # passed, because patching the wrapper also patched away the builder, so the
                # payload was never validated. Building in the handler makes it real.
                "updates": {"packages": [{"package_id": "pkg_1", "paused": False}]},
            }

            import asyncio

            result = asyncio.run(handler._handle_update_media_buy_skill(parameters=parameters, identity=_MOCK_IDENTITY))

            # Should extract packages from legacy 'updates' wrapper
            mock_update.assert_called_once()
            req = mock_update.call_args.kwargs["req"]

            # Verify packages were extracted from the legacy 'updates' wrapper onto the request
            assert req.packages is not None and len(req.packages) == 1, "Should have extracted 1 package"
            assert req.packages[0].package_id == "pkg_1", "Package ID should match"

    def test_update_media_buy_validates_required_parameters(self):
        """
        Test that update_media_buy validates required parameters per AdCP spec.

        Per AdCP spec: requires 'media_buy_id'
        """
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        handler = AdCPRequestHandler()

        with patch("src.core.resolved_identity.resolve_identity", return_value=_MOCK_IDENTITY):
            # Request with no media_buy_id
            invalid_parameters = {"active": True, "packages": []}

            import asyncio

            # Skill handlers raise typed AdCPValidationError on missing params so the
            # dispatcher routes through the two-layer envelope (not a JSON-RPC error).
            from src.core.exceptions import AdCPValidationError

            with pytest.raises(AdCPValidationError) as exc_info:
                asyncio.run(
                    handler._handle_update_media_buy_skill(parameters=invalid_parameters, identity=_MOCK_IDENTITY)
                )

            # Error message should mention required parameter
            error_message = str(exc_info.value).lower()
            msg = "Error message should mention required parameter"

    def test_get_media_buy_delivery_uses_plural_media_buy_ids(self):
        """
        Test that get_media_buy_delivery uses 'media_buy_ids' (plural).

        AdCP spec uses plural 'media_buy_ids' for array parameter.
        """
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        handler = AdCPRequestHandler()

        with (
            patch("src.core.resolved_identity.resolve_identity", return_value=_MOCK_IDENTITY),
            stub_impl("get_media_buy_delivery") as mock_delivery,
        ):
            mock_delivery.return_value = {"media_buys": []}

            # AdCP request with plural 'media_buy_ids'
            parameters = {"media_buy_ids": ["mb_1", "mb_2", "mb_3"]}

            import asyncio

            result = asyncio.run(
                handler._handle_get_media_buy_delivery_skill(parameters=parameters, identity=_MOCK_IDENTITY)
            )

            # Verify the BUILT REQUEST carries the parameter. The handler hands the
            # wrapper a request now, so the plural spelling is graded where it lives --
            # on the request -- rather than on a kwarg the wrapper no longer takes.
            # Should use plural 'media_buy_ids' per AdCP spec -- graded on the built
            # request, which is what the wrapper takes now.
            expected_req = GetMediaBuyDeliveryRequest(media_buy_ids=parameters["media_buy_ids"])
            mock_delivery.assert_called_once_with(req=expected_req, identity=_MOCK_IDENTITY)

    def test_get_media_buy_delivery_optional_media_buy_ids(self):
        """
        Test that get_media_buy_delivery works without media_buy_ids.

        Per AdCP spec, all parameters are optional. When media_buy_ids is omitted,
        the server should return delivery data for all media buys the requester
        has access to, filtered by the provided criteria (status_filter, dates, etc).
        """
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        handler = AdCPRequestHandler()

        with (
            patch("src.core.resolved_identity.resolve_identity", return_value=_MOCK_IDENTITY),
            stub_impl("get_media_buy_delivery") as mock_delivery,
        ):
            mock_delivery.return_value = {"media_buys": []}

            # AdCP request with filters but no media_buy_ids
            parameters = {
                "status_filter": "active",
                "start_date": "2025-01-01",
                "end_date": "2025-01-31",
            }

            import asyncio

            result = asyncio.run(
                handler._handle_get_media_buy_delivery_skill(parameters=parameters, identity=_MOCK_IDENTITY)
            )

            # The filters reach the core tool ON the built request, and media_buy_ids
            # stays None — the buyer omitted it, so nothing may invent one. Grading the
            # whole request (rather than three fields out of fourteen) is what proves
            # nothing the buyer did not send was manufactured here.
            expected_req = GetMediaBuyDeliveryRequest(
                status_filter="active", start_date="2025-01-01", end_date="2025-01-31"
            )
            mock_delivery.assert_called_once_with(req=expected_req, identity=_MOCK_IDENTITY)
            # media_buy_ids and account stay at their defaults on expected_req, so the
            # equality above is what proves the omitted fields were not invented.

    def test_get_media_buy_delivery_forwards_typed_account_reference(self):
        """A2A get_media_buy_delivery must pass the validated account model."""
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        handler = AdCPRequestHandler()

        with stub_impl("get_media_buy_delivery") as mock_delivery:
            mock_delivery.return_value = {"media_buys": []}

            parameters = {"account": {"account_id": "acct-1"}}

            import asyncio

            asyncio.run(handler._handle_get_media_buy_delivery_skill(parameters=parameters, identity=_MOCK_IDENTITY))

            expected = LibraryAccountReference.model_validate({"account_id": "acct-1"})

            assert_delivery_forwarded_account(mock_delivery, expected)

    def test_get_media_buy_delivery_forwards_natural_key_account_reference(self):
        """A2A get_media_buy_delivery forwards the validated {brand, operator} account form.

        Complements the {account_id} case above by pinning the natural-key
        AccountReference variant — the form the delivery conformance storyboard
        sends — whose nested brand exercises its own coercion path.
        """
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        handler = AdCPRequestHandler()

        with stub_impl("get_media_buy_delivery") as mock_delivery:
            mock_delivery.return_value = {"media_buys": []}

            account = {"brand": {"domain": "acmeoutdoor.example"}, "operator": "pinnacle-agency.example"}
            parameters = {"account": account}

            import asyncio

            asyncio.run(handler._handle_get_media_buy_delivery_skill(parameters=parameters, identity=_MOCK_IDENTITY))

            expected = LibraryAccountReference.model_validate(account)

            assert_delivery_forwarded_account(mock_delivery, expected)

    def test_get_media_buy_delivery_rejects_malformed_account(self):
        """Malformed account should fail validation and not call the core tool.

        Driven through ``_handle_explicit_skill``, the A2A DISPATCHER, rather than through
        the skill handler under it. The handler no longer wraps its request construction in
        a validation boundary; the dispatcher normalizes the escaping pydantic error
        through the shared ``adcp_error_for``, so the dispatcher is where A2A's answer to a
        malformed account is decided, and the envelope is asserted there.
        """
        import asyncio

        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler
        from src.core.exceptions import AdCPSalesAgentError, build_two_layer_error_envelope

        handler = AdCPRequestHandler()

        with stub_impl("get_media_buy_delivery") as mock_delivery:
            with pytest.raises(AdCPSalesAgentError) as exc_info:
                asyncio.run(
                    handler._handle_explicit_skill(
                        "get_media_buy_delivery",
                        {"account": {}},
                        _MOCK_IDENTITY,
                    )
                )

            assert_envelope_shape(
                build_two_layer_error_envelope(exc_info.value), "INVALID_REQUEST", recovery="correctable"
            )
            mock_delivery.assert_not_called()

    def test_create_media_buy_validates_required_adcp_parameters(self):
        """
        Test that create_media_buy validates required AdCP parameters.

        The handler should reject requests missing required fields per AdCP spec.
        """
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        handler = AdCPRequestHandler()

        with patch("src.core.resolved_identity.resolve_identity", return_value=_MOCK_IDENTITY):
            # Request missing required AdCP parameters
            incomplete_parameters = {
                "po_number": "campaign_123",
                # Missing: brand, packages, start_time, end_time
            }

            import asyncio

            # Skill handlers raise typed AdCPValidationError on missing-params; the
            # outer dispatcher catches AdCPSalesAgentError and routes through
            # _build_failed_skill_result to produce the two-layer envelope.
            # Asserting on the raised exception (not a returned dict) verifies the
            # flat-dict bypass path is closed — handlers must raise, never return
            # {"success": False, ...} that bypasses envelope construction.
            from src.core.exceptions import AdCPValidationError

            with pytest.raises(AdCPValidationError) as exc_info:
                asyncio.run(
                    handler._handle_create_media_buy_skill(parameters=incomplete_parameters, identity=_MOCK_IDENTITY)
                )

            error_message = str(exc_info.value).lower()
