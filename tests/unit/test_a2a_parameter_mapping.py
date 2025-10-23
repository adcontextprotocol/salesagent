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

        # Mock at the right level - mock the update_media_buy_raw import in a2a_server
        with (
            patch("src.a2a_server.adcp_a2a_server.get_principal_from_token") as mock_principal,
            patch("src.a2a_server.adcp_a2a_server.get_current_tenant") as mock_tenant,
            patch("src.a2a_server.adcp_a2a_server.core_update_media_buy_tool") as mock_update,
        ):
            mock_principal.return_value = "principal_123"
            mock_tenant.return_value = {"tenant_id": "tenant_123"}
            mock_update.return_value = {"status": "success", "media_buy_id": "mb_123"}

            # Simulate A2A request with AdCP v2.0+ 'packages' field
            parameters = {
                "media_buy_id": "mb_123",
                "active": True,
                "packages": [{"package_id": "pkg_1", "active": True}],  # AdCP v2.0+ field name
            }

            # Call the skill handler (synchronous wrapper for async method)
            import asyncio

            result = asyncio.run(handler._handle_update_media_buy_skill(parameters=parameters, auth_token="test_token"))

            # Verify the core function was called with correct parameter name
            mock_update.assert_called_once()
            call_kwargs = mock_update.call_args.kwargs

            # CRITICAL: Must pass 'packages' parameter (not 'updates')
            assert "packages" in call_kwargs, "Core function should be called with 'packages' parameter (AdCP v2.0+)"
            assert call_kwargs["packages"] == parameters["packages"], "Packages data should be passed through correctly"

            # Should NOT use legacy 'updates' parameter
            assert "updates" not in call_kwargs, "Should not pass legacy 'updates' parameter to core function"

            # Verify other AdCP v2.0+ parameters are passed
            assert call_kwargs["media_buy_id"] == "mb_123"
            assert call_kwargs["active"] is True

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
            patch("src.a2a_server.adcp_a2a_server.get_principal_from_token") as mock_principal,
            patch("src.a2a_server.adcp_a2a_server.get_current_tenant") as mock_tenant,
            patch("src.a2a_server.adcp_a2a_server.core_update_media_buy_tool") as mock_update,
        ):
            mock_principal.return_value = "principal_123"
            mock_tenant.return_value = {"tenant_id": "tenant_123"}
            mock_update.return_value = {"status": "success"}

            # Legacy request format with 'updates' wrapper
            parameters = {
                "media_buy_id": "mb_123",
                "updates": {"packages": [{"package_id": "pkg_1", "budget": 5000.0}]},  # Legacy wrapper
            }

            import asyncio

            result = asyncio.run(handler._handle_update_media_buy_skill(parameters=parameters, auth_token="test_token"))

            # Should extract packages from legacy 'updates' wrapper
            mock_update.assert_called_once()
            call_kwargs = mock_update.call_args.kwargs

            assert (
                call_kwargs["packages"] == parameters["updates"]["packages"]
            ), "Should extract packages from legacy 'updates' wrapper"

    def test_update_media_buy_validates_required_parameters(self):
        """
        Test that update_media_buy validates required parameters per AdCP spec.

        Per AdCP oneOf constraint: requires either 'media_buy_id' OR 'buyer_ref'
        """
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        handler = AdCPRequestHandler()

        with (
            patch("src.a2a_server.adcp_a2a_server.get_principal_from_token") as mock_principal,
            patch("src.a2a_server.adcp_a2a_server.get_current_tenant") as mock_tenant,
        ):
            mock_principal.return_value = "principal_123"
            mock_tenant.return_value = {"tenant_id": "tenant_123"}

            # Request with neither media_buy_id nor buyer_ref
            invalid_parameters = {"active": True, "packages": []}

            import asyncio

            result = asyncio.run(
                handler._handle_update_media_buy_skill(parameters=invalid_parameters, auth_token="test_token")
            )

            # Should return error for missing required parameter
            assert result["success"] is False, "Should reject request without media_buy_id or buyer_ref"
            assert (
                "media_buy_id" in result["message"].lower() or "buyer_ref" in result["message"].lower()
            ), "Error message should mention required parameter"

    def test_get_media_buy_delivery_uses_plural_media_buy_ids(self):
        """
        Test that get_media_buy_delivery uses 'media_buy_ids' (plural).

        AdCP spec uses plural 'media_buy_ids' for array parameter.
        """
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        handler = AdCPRequestHandler()

        with (
            patch("src.a2a_server.adcp_a2a_server.get_principal_from_token") as mock_principal,
            patch("src.a2a_server.adcp_a2a_server.get_current_tenant") as mock_tenant,
            patch("src.a2a_server.adcp_a2a_server.core_get_media_buy_delivery_tool") as mock_delivery,
        ):
            mock_principal.return_value = "principal_123"
            mock_tenant.return_value = {"tenant_id": "tenant_123"}
            mock_delivery.return_value = {"media_buys": []}

            # AdCP request with plural 'media_buy_ids'
            parameters = {"media_buy_ids": ["mb_1", "mb_2", "mb_3"]}

            import asyncio

            result = asyncio.run(
                handler._handle_get_media_buy_delivery_skill(parameters=parameters, auth_token="test_token")
            )

            # Verify core function was called with correct parameter
            mock_delivery.assert_called_once()
            call_kwargs = mock_delivery.call_args.kwargs

            # Should use plural 'media_buy_ids' per AdCP spec
            assert "media_buy_ids" in call_kwargs, "Should pass 'media_buy_ids' (plural) per AdCP spec"
            assert call_kwargs["media_buy_ids"] == parameters["media_buy_ids"]

    def test_create_media_buy_validates_required_adcp_parameters(self):
        """
        Test that create_media_buy validates required AdCP parameters.

        The handler should reject requests missing required fields per AdCP spec.
        """
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        handler = AdCPRequestHandler()

        with (
            patch("src.a2a_server.adcp_a2a_server.get_principal_from_token") as mock_principal,
            patch("src.a2a_server.adcp_a2a_server.get_current_tenant") as mock_tenant,
        ):
            mock_principal.return_value = "principal_123"
            mock_tenant.return_value = {"tenant_id": "tenant_123"}

            # Request missing required AdCP parameters
            incomplete_parameters = {
                "buyer_ref": "campaign_123",
                # Missing: brand_manifest, packages, budget, start_time, end_time
            }

            import asyncio

            result = asyncio.run(
                handler._handle_create_media_buy_skill(parameters=incomplete_parameters, auth_token="test_token")
            )

            # Should reject and list missing required parameters
            assert result["success"] is False, "Should reject request missing required AdCP parameters"
            assert "brand_manifest" in str(result.get("message", "")).lower() or "brand_manifest" in str(
                result.get("required_parameters", [])
            ), "Error should mention missing 'brand_manifest'"
            assert "packages" in str(result.get("required_parameters", [])), "Error should mention missing 'packages'"
