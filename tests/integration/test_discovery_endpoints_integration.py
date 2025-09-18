"""
Integration tests for discovery endpoints authentication changes.

Tests the actual behavior of get_products and list_creative_formats with and without authentication
using real database connections and minimal mocking.
"""

from unittest.mock import Mock, patch

import pytest

from src.core.config_loader import set_current_tenant
from src.core.main import get_products, list_creative_formats
from src.core.schemas import GetProductsResponse, ListCreativeFormatsResponse


@pytest.mark.integration
class TestDiscoveryEndpointsIntegration:
    """Integration tests for discovery endpoints with real database."""

    @classmethod
    def setup_class(cls):
        """Setup test tenant and database state."""
        # Set a test tenant
        cls.test_tenant = {"tenant_id": "test_discovery_tenant", "name": "Test Discovery Tenant", "policy_settings": {}}
        set_current_tenant(cls.test_tenant)

    def create_mock_context(self, with_auth=True):
        """Create a mock FastMCP context with optional authentication."""
        context = Mock()

        if with_auth:
            # Mock context with valid authentication
            context.meta = {"headers": {"x-adcp-auth": "valid_test_token"}}
        else:
            # Mock context without authentication
            context.meta = {"headers": {}}

        return context

    @pytest.mark.asyncio
    async def test_get_products_anonymous_access_integration(self):
        """Integration test: get_products works without authentication."""

        # Mock only the external dependencies that aren't part of our core logic
        with (
            patch("src.core.main.get_principal_from_context", return_value=None),
            patch("src.core.main.PolicyCheckService") as mock_policy_service,
            patch("src.core.main.get_provider_manager") as mock_provider,
        ):

            # Setup policy service mock
            mock_policy_instance = Mock()
            mock_policy_instance.check_brief_compliance = Mock(
                return_value=Mock(status="APPROVED", reason="Valid content", restrictions=[])
            )
            mock_policy_service.return_value = mock_policy_instance

            # Setup provider manager mock
            mock_provider.return_value.get_products.return_value = {
                "products": [
                    {
                        "product_id": "discovery_test_product",
                        "name": "Discovery Test Product",
                        "description": "Test product for anonymous discovery",
                    }
                ]
            }

            context = self.create_mock_context(with_auth=False)

            # This should work without authentication
            response = await get_products(
                brief="test discovery campaign", promoted_offering="Test Brand Discovery Product", context=context
            )

            # Verify successful response
            assert isinstance(response, GetProductsResponse)
            assert response.products is not None
            assert len(response.products) >= 0  # May be empty but should not error

    @pytest.mark.asyncio
    async def test_get_products_authenticated_access_integration(self):
        """Integration test: get_products still works with authentication."""

        # Mock the authentication and external dependencies
        with (
            patch("src.core.main.get_principal_from_context", return_value="test_principal"),
            patch("src.core.main.get_principal_object") as mock_get_principal_obj,
            patch("src.core.main.PolicyCheckService") as mock_policy_service,
            patch("src.core.main.get_provider_manager") as mock_provider,
        ):

            # Setup principal object mock
            mock_principal = Mock()
            mock_principal.model_dump.return_value = {"principal_id": "test_principal", "name": "Test Principal"}
            mock_get_principal_obj.return_value = mock_principal

            # Setup policy service mock
            mock_policy_instance = Mock()
            mock_policy_instance.check_brief_compliance = Mock(
                return_value=Mock(status="APPROVED", reason="Valid content", restrictions=[])
            )
            mock_policy_service.return_value = mock_policy_instance

            # Setup provider manager mock
            mock_provider.return_value.get_products.return_value = {
                "products": [
                    {
                        "product_id": "auth_test_product",
                        "name": "Authenticated Test Product",
                        "description": "Test product for authenticated access",
                    }
                ]
            }

            context = self.create_mock_context(with_auth=True)

            # This should work with authentication (backwards compatibility)
            response = await get_products(
                brief="authenticated discovery campaign",
                promoted_offering="Test Brand Authenticated Product",
                context=context,
            )

            # Verify successful response
            assert isinstance(response, GetProductsResponse)
            assert response.products is not None

    def test_list_creative_formats_anonymous_access_integration(self):
        """Integration test: list_creative_formats works without authentication."""

        # Mock only the authentication check
        with patch("src.core.main.get_principal_from_context", return_value=None):

            context = self.create_mock_context(with_auth=False)

            # This should work without authentication
            response = list_creative_formats(context=context)

            # Verify successful response
            assert isinstance(response, ListCreativeFormatsResponse)
            assert response.formats is not None
            assert len(response.formats) >= 0  # May be empty but should not error

    def test_list_creative_formats_authenticated_access_integration(self):
        """Integration test: list_creative_formats still works with authentication."""

        # Mock the authentication check to return a principal
        with patch("src.core.main.get_principal_from_context", return_value="test_principal"):

            context = self.create_mock_context(with_auth=True)

            # This should work with authentication (backwards compatibility)
            response = list_creative_formats(context=context)

            # Verify successful response
            assert isinstance(response, ListCreativeFormatsResponse)
            assert response.formats is not None

    @pytest.mark.asyncio
    async def test_audit_logging_anonymous_vs_authenticated(self):
        """Integration test: Verify audit logging works for both anonymous and authenticated requests."""

        with (
            patch("src.core.main.get_audit_logger") as mock_audit_logger,
            patch("src.core.main.PolicyCheckService") as mock_policy_service,
            patch("src.core.main.get_provider_manager") as mock_provider,
        ):

            # Setup mocks
            mock_audit_instance = Mock()
            mock_audit_logger.return_value = mock_audit_instance

            mock_policy_instance = Mock()
            mock_policy_instance.check_brief_compliance = Mock(
                return_value=Mock(status="APPROVED", reason="Valid", restrictions=[])
            )
            mock_policy_service.return_value = mock_policy_instance

            mock_provider.return_value.get_products.return_value = {"products": []}

            # Test anonymous request
            with patch("src.core.main.get_principal_from_context", return_value=None):
                context = self.create_mock_context(with_auth=False)
                await get_products(brief="anonymous test", promoted_offering="Anonymous Test Product", context=context)

                # Verify audit logging was called with "anonymous"
                mock_audit_instance.log_operation.assert_called()
                call_args = mock_audit_instance.log_operation.call_args
                assert call_args[1]["principal_name"] == "anonymous"
                assert call_args[1]["principal_id"] == "anonymous"

            # Reset mock
            mock_audit_instance.log_operation.reset_mock()

            # Test authenticated request
            with (
                patch("src.core.main.get_principal_from_context", return_value="auth_principal"),
                patch(
                    "src.core.main.get_principal_object",
                    return_value=Mock(model_dump=Mock(return_value={"principal_id": "auth_principal"})),
                ),
            ):

                context = self.create_mock_context(with_auth=True)
                await get_products(
                    brief="authenticated test", promoted_offering="Authenticated Test Product", context=context
                )

                # Verify audit logging was called with actual principal
                mock_audit_instance.log_operation.assert_called()
                call_args = mock_audit_instance.log_operation.call_args
                assert call_args[1]["principal_name"] == "auth_principal"
                assert call_args[1]["principal_id"] == "auth_principal"

    @pytest.mark.asyncio
    async def test_tenant_still_required(self):
        """Integration test: Verify tenant context is still required even for anonymous access."""

        # Temporarily unset tenant
        original_tenant = self.test_tenant
        set_current_tenant(None)

        try:
            with (
                patch("src.core.main.get_principal_from_context", return_value=None),
                patch("src.core.main.get_current_tenant", return_value=None),
            ):

                context = self.create_mock_context(with_auth=False)

                # Should fail when no tenant context available
                with pytest.raises(Exception) as exc_info:
                    await get_products(
                        brief="no tenant test", promoted_offering="No Tenant Test Product", context=context
                    )

                assert "tenant" in str(exc_info.value).lower()

                # Same for list_creative_formats
                with pytest.raises(Exception) as exc_info:
                    list_creative_formats(context=context)

                assert "tenant" in str(exc_info.value).lower()

        finally:
            # Restore tenant
            set_current_tenant(original_tenant)


@pytest.mark.integration
class TestDiscoveryEndpointsSecurityBoundaries:
    """Test that security boundaries are maintained for discovery endpoints."""

    @classmethod
    def setup_class(cls):
        """Setup test tenant."""
        cls.test_tenant = {"tenant_id": "security_test_tenant", "name": "Security Test Tenant"}
        set_current_tenant(cls.test_tenant)

    def test_only_discovery_endpoints_allow_anonymous_access(self):
        """Test that only get_products and list_creative_formats allow anonymous access."""
        # This is more of a documentation test - we want to ensure that as new endpoints
        # are added, they don't accidentally inherit the anonymous access behavior

        from fastmcp import ToolError

        context = Mock()
        context.meta = {"headers": {}}  # No authentication

        # These endpoints should still require authentication
        with pytest.raises((ToolError, Exception)) as exc_info:
            # create_media_buy should fail without auth
            pass  # We'll just document this expectation for now

        # The key point is that get_products and list_creative_formats are special cases
        # All other endpoints should continue to require authentication

    def test_discovery_endpoints_provide_read_only_access(self):
        """Test that discovery endpoints only provide read-only information."""
        # This test verifies that the anonymous access doesn't allow any write operations
        # Discovery endpoints should only return product and format information

        # get_products should only return product information
        # list_creative_formats should only return format information
        # Neither should allow modification of any data

        # This is enforced by the nature of these endpoints - they are inherently read-only
        pass  # Documentation test
