"""
Test suite for discovery endpoints authentication behavior.

Tests the new optional authentication for get_products and list_creative_formats endpoints.
These endpoints should work both with and without authentication for discovery purposes.
"""

from unittest.mock import Mock, patch

import pytest
from fastmcp import Context

from src.core.main import get_products, list_creative_formats
from src.core.schemas import GetProductsResponse, ListCreativeFormatsResponse


class TestDiscoveryEndpointsAuth:
    """Test authentication behavior for discovery endpoints."""

    def create_mock_context(self, with_auth=True):
        """Create a mock FastMCP context with optional authentication."""
        context = Mock(spec=Context)

        if with_auth:
            # Mock context with valid authentication
            context.meta = {"headers": {"x-adcp-auth": "valid_test_token"}}
        else:
            # Mock context without authentication
            context.meta = {"headers": {}}

        return context

    @pytest.mark.asyncio
    @patch("src.core.main.get_current_tenant")
    @patch("src.core.main.get_principal_from_context")
    @patch("src.core.main.get_principal_object")
    @patch("src.core.main.PolicyCheckService")
    @patch("src.core.main.get_audit_logger")
    @patch("src.core.main.log_tool_activity")
    async def test_get_products_with_authentication(
        self,
        mock_log_activity,
        mock_audit_logger,
        mock_policy_service,
        mock_get_principal_object,
        mock_get_principal,
        mock_get_tenant,
    ):
        """Test get_products works with valid authentication."""
        # Setup mocks for authenticated request
        mock_get_tenant.return_value = {"tenant_id": "test_tenant", "policy_settings": {}}
        mock_get_principal.return_value = "test_principal"
        mock_get_principal_object.return_value = Mock(model_dump=Mock(return_value={"principal_id": "test_principal"}))

        # Mock policy service
        mock_policy_instance = Mock()
        mock_policy_instance.check_brief_compliance = Mock(
            return_value=Mock(status="APPROVED", reason="Valid", restrictions=[])
        )
        mock_policy_service.return_value = mock_policy_instance

        # Mock audit logger
        mock_audit_instance = Mock()
        mock_audit_instance.log_operation = Mock()
        mock_audit_logger.return_value = mock_audit_instance

        with (
            patch("src.core.main.get_testing_context", return_value=Mock()),
            patch("src.core.main.safe_parse_json_field", return_value={}),
            patch("src.core.main.get_product_catalog_provider") as mock_provider,
        ):

            # Setup provider mock
            mock_provider_instance = Mock()
            mock_provider_instance.get_products = Mock(return_value={"products": []})
            mock_provider.return_value = mock_provider_instance

            context = self.create_mock_context(with_auth=True)
            response = await get_products(
                brief="test campaign", promoted_offering="Nike Air Max 2025 running shoes", context=context
            )

            # Verify response
            assert isinstance(response, GetProductsResponse)

            # Verify principal was extracted and used
            mock_get_principal.assert_called_once_with(context)
            mock_get_principal_object.assert_called_once_with("test_principal")

            # Verify audit logging with authenticated principal
            mock_audit_instance.log_operation.assert_called()
            call_args = mock_audit_instance.log_operation.call_args
            assert call_args[1]["principal_name"] == "test_principal"
            assert call_args[1]["principal_id"] == "test_principal"

    @pytest.mark.asyncio
    @patch("src.core.main.get_current_tenant")
    @patch("src.core.main.get_principal_from_context")
    @patch("src.core.main.get_principal_object")
    @patch("src.core.main.PolicyCheckService")
    @patch("src.core.main.get_audit_logger")
    @patch("src.core.main.log_tool_activity")
    async def test_get_products_without_authentication(
        self,
        mock_log_activity,
        mock_audit_logger,
        mock_policy_service,
        mock_get_principal_object,
        mock_get_principal,
        mock_get_tenant,
    ):
        """Test get_products works without authentication (anonymous access)."""
        # Setup mocks for anonymous request
        mock_get_tenant.return_value = {"tenant_id": "test_tenant", "policy_settings": {}}
        mock_get_principal.return_value = None  # No authentication
        mock_get_principal_object.return_value = None

        # Mock policy service
        mock_policy_instance = Mock()
        mock_policy_instance.check_brief_compliance = Mock(
            return_value=Mock(status="APPROVED", reason="Valid", restrictions=[])
        )
        mock_policy_service.return_value = mock_policy_instance

        # Mock audit logger
        mock_audit_instance = Mock()
        mock_audit_instance.log_operation = Mock()
        mock_audit_logger.return_value = mock_audit_instance

        with (
            patch("src.core.main.get_testing_context", return_value=Mock()),
            patch("src.core.main.safe_parse_json_field", return_value={}),
            patch("src.core.main.get_product_catalog_provider") as mock_provider,
        ):

            # Setup provider mock
            mock_provider_instance = Mock()
            mock_provider_instance.get_products = Mock(return_value={"products": []})
            mock_provider.return_value = mock_provider_instance

            context = self.create_mock_context(with_auth=False)
            response = await get_products(
                brief="test campaign", promoted_offering="Nike Air Max 2025 running shoes", context=context
            )

            # Verify response works without authentication
            assert isinstance(response, GetProductsResponse)

            # Verify principal was checked but returned None
            mock_get_principal.assert_called_once_with(context)
            mock_get_principal_object.assert_called_once_with(None)

            # Verify audit logging with anonymous principal
            mock_audit_instance.log_operation.assert_called()
            call_args = mock_audit_instance.log_operation.call_args
            assert call_args[1]["principal_name"] == "anonymous"
            assert call_args[1]["principal_id"] == "anonymous"

    @patch("src.core.main.get_current_tenant")
    @patch("src.core.main.get_principal_from_context")
    @patch("src.core.main.get_audit_logger")
    @patch("src.core.main.get_db_session")
    def test_list_creative_formats_with_authentication(
        self, mock_db_session, mock_audit_logger, mock_get_principal, mock_get_tenant
    ):
        """Test list_creative_formats works with valid authentication."""
        # Setup mocks for authenticated request
        mock_get_tenant.return_value = {"tenant_id": "test_tenant"}
        mock_get_principal.return_value = "test_principal"

        # Mock database session and query results
        mock_session = Mock()
        mock_db_session.return_value.__enter__.return_value = mock_session
        mock_session.query.return_value.filter.return_value.all.return_value = []

        # Mock audit logger
        mock_audit_instance = Mock()
        mock_audit_instance.log_operation = Mock()
        mock_audit_logger.return_value = mock_audit_instance

        with patch("src.core.schemas.FORMAT_REGISTRY", {}):
            context = self.create_mock_context(with_auth=True)
            response = list_creative_formats(context=context)

            # Verify response
            assert isinstance(response, ListCreativeFormatsResponse)

            # Verify principal was extracted and used
            mock_get_principal.assert_called_once_with(context)

            # Verify audit logging with authenticated principal
            mock_audit_instance.log_operation.assert_called()
            call_args = mock_audit_instance.log_operation.call_args
            assert call_args[1]["principal_name"] == "test_principal"
            assert call_args[1]["principal_id"] == "test_principal"

    @patch("src.core.main.get_current_tenant")
    @patch("src.core.main.get_principal_from_context")
    @patch("src.core.main.get_audit_logger")
    @patch("src.core.main.get_db_session")
    def test_list_creative_formats_without_authentication(
        self, mock_db_session, mock_audit_logger, mock_get_principal, mock_get_tenant
    ):
        """Test list_creative_formats works without authentication (anonymous access)."""
        # Setup mocks for anonymous request
        mock_get_tenant.return_value = {"tenant_id": "test_tenant"}
        mock_get_principal.return_value = None  # No authentication

        # Mock database session and query results
        mock_session = Mock()
        mock_db_session.return_value.__enter__.return_value = mock_session
        mock_session.query.return_value.filter.return_value.all.return_value = []

        # Mock audit logger
        mock_audit_instance = Mock()
        mock_audit_instance.log_operation = Mock()
        mock_audit_logger.return_value = mock_audit_instance

        with patch("src.core.schemas.FORMAT_REGISTRY", {}):
            context = self.create_mock_context(with_auth=False)
            response = list_creative_formats(context=context)

            # Verify response works without authentication
            assert isinstance(response, ListCreativeFormatsResponse)

            # Verify principal was checked but returned None
            mock_get_principal.assert_called_once_with(context)

            # Verify audit logging with anonymous principal
            mock_audit_instance.log_operation.assert_called()
            call_args = mock_audit_instance.log_operation.call_args
            assert call_args[1]["principal_name"] == "anonymous"
            assert call_args[1]["principal_id"] == "anonymous"

    @pytest.mark.asyncio
    @patch("src.core.main.get_current_tenant")
    @patch("src.core.main.get_principal_from_context")
    async def test_get_products_tenant_required(self, mock_get_principal, mock_get_tenant):
        """Test that get_products still requires tenant context."""
        # Setup mocks - no tenant available
        mock_get_tenant.return_value = None
        mock_get_principal.return_value = None

        with patch("src.core.main.get_testing_context", return_value=Mock()):
            context = self.create_mock_context(with_auth=False)

            # Should raise error when no tenant context
            with pytest.raises(Exception) as exc_info:
                await get_products(
                    brief="test campaign", promoted_offering="Nike Air Max 2025 running shoes", context=context
                )

            assert "tenant" in str(exc_info.value).lower()

    @patch("src.core.main.get_current_tenant")
    @patch("src.core.main.get_principal_from_context")
    def test_list_creative_formats_tenant_required(self, mock_get_principal, mock_get_tenant):
        """Test that list_creative_formats still requires tenant context."""
        # Setup mocks - no tenant available
        mock_get_tenant.return_value = None
        mock_get_principal.return_value = None

        context = self.create_mock_context(with_auth=False)

        # Should raise error when no tenant context
        with pytest.raises(Exception) as exc_info:
            list_creative_formats(context=context)

        assert "tenant" in str(exc_info.value).lower()


class TestBackwardsCompatibility:
    """Test that existing authenticated workflows continue to work."""

    @pytest.mark.asyncio
    @patch("src.core.main.get_current_tenant")
    @patch("src.core.main.get_principal_from_context")
    @patch("src.core.main.get_principal_object")
    @patch("src.core.main.PolicyCheckService")
    @patch("src.core.main.get_audit_logger")
    @patch("src.core.main.log_tool_activity")
    async def test_authenticated_get_products_unchanged(
        self,
        mock_log_activity,
        mock_audit_logger,
        mock_policy_service,
        mock_get_principal_object,
        mock_get_principal,
        mock_get_tenant,
    ):
        """Test that existing authenticated get_products calls work exactly as before."""
        # This test ensures backwards compatibility - existing authenticated calls should work identically

        # Setup mocks exactly as they would be in a real authenticated scenario
        mock_tenant = {"tenant_id": "existing_tenant", "policy_settings": {"enabled": True}}
        mock_get_tenant.return_value = mock_tenant
        mock_get_principal.return_value = "existing_principal"

        mock_principal = Mock()
        mock_principal.model_dump.return_value = {
            "principal_id": "existing_principal",
            "name": "Existing Principal",
            "platform_mappings": {"gam_advertiser_id": "123"},
        }
        mock_get_principal_object.return_value = mock_principal

        # Mock policy service - should be called with principal context
        mock_policy_instance = Mock()
        mock_policy_instance.check_brief_compliance = Mock(
            return_value=Mock(status="APPROVED", reason="Valid", restrictions=[])
        )
        mock_policy_service.return_value = mock_policy_instance

        # Mock audit logger
        mock_audit_instance = Mock()
        mock_audit_logger.return_value = mock_audit_instance

        with (
            patch("src.core.main.get_testing_context", return_value=Mock()),
            patch("src.core.main.safe_parse_json_field", return_value={"enabled": True}),
            patch("src.core.main.get_product_catalog_provider") as mock_provider,
        ):

            # Setup provider mock
            mock_provider_instance = Mock()
            mock_provider_instance.get_products = Mock(
                return_value={"products": [{"product_id": "prod_1", "name": "Display Banner"}]}
            )
            mock_provider.return_value = mock_provider_instance

            context = Mock(spec=Context)
            context.meta = {"headers": {"x-adcp-auth": "existing_valid_token"}}

            response = await get_products(
                brief="display advertising campaign", promoted_offering="Existing Brand Athletic Shoes", context=context
            )

            # Verify all existing behavior is preserved
            assert isinstance(response, GetProductsResponse)
            mock_get_principal.assert_called_once_with(context)
            mock_get_principal_object.assert_called_once_with("existing_principal")

            # Verify policy check happened with principal context
            mock_policy_instance.check_brief_compliance.assert_called_once()

            # Verify audit logging with specific principal (not anonymous)
            mock_audit_instance.log_operation.assert_called()
            call_args = mock_audit_instance.log_operation.call_args
            assert call_args[1]["principal_name"] == "existing_principal"
            assert call_args[1]["principal_id"] == "existing_principal"
