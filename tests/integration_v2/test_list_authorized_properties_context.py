#!/usr/bin/env python3
"""
Integration test for list_authorized_properties context handling.

This test specifically exercises the context handling and testing hooks
that caused the NameError bug in production.

Tests:
- Real code path execution with context objects
- Testing context extraction from FastMCP headers
- ToolContext vs FastMCP Context handling
- Import verification of get_testing_context
"""

from unittest.mock import Mock

import pytest

from src.core.database.database_session import get_db_session
from src.core.database.models import AuthorizedProperty, Tenant
from src.core.schema_adapters import ListAuthorizedPropertiesRequest, ListAuthorizedPropertiesResponse
from src.core.tool_context import ToolContext
from src.core.tools.properties import _list_authorized_properties_impl

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]


class TestListAuthorizedPropertiesContext:
    """Test list_authorized_properties with different context types."""

    def test_with_tool_context(self, integration_db):
        """Test list_authorized_properties with ToolContext (A2A path)."""
        # Create test tenant and property
        with get_db_session() as session:
            tenant = Tenant(
                tenant_id="test_tenant_ctx",
                name="Test Tenant",
                subdomain="test-ctx",
            )
            session.add(tenant)
            session.flush()

            prop = AuthorizedProperty(
                property_id="prop_ctx_001",
                tenant_id=tenant.tenant_id,
                property_type="website",
                name="Test Site",
                identifiers=[{"type": "domain", "value": "example-ctx.com"}],
                tags=["test"],
                publisher_domain="example-ctx.com",
                verification_status="verified",
            )
            session.add(prop)
            session.commit()

        # Create ToolContext with testing_context
        context = ToolContext(
            tenant_id="test_tenant_ctx",
            principal_id="test_principal",
            testing_context={"dry_run": True, "test_session_id": "test_123"},
        )

        # Execute - this should handle ToolContext path
        req = ListAuthorizedPropertiesRequest()
        response = _list_authorized_properties_impl(req, context)

        # Verify response
        assert isinstance(response, ListAuthorizedPropertiesResponse)
        assert "example-ctx.com" in response.publisher_domains
        assert response.errors == []

    def test_with_fastmcp_context(self, integration_db):
        """Test list_authorized_properties with FastMCP Context (MCP path).

        This test exercises the code path that had the bug:
        - FastMCP Context with meta.headers
        - Calls get_testing_context(context)
        - Previously failed with NameError
        """
        # Create test tenant and property
        with get_db_session() as session:
            tenant = Tenant(
                tenant_id="test_tenant_mcp",
                name="Test Tenant MCP",
                subdomain="test-mcp",
            )
            session.add(tenant)
            session.flush()

            prop = AuthorizedProperty(
                property_id="prop_mcp_001",
                tenant_id=tenant.tenant_id,
                property_type="website",
                name="Test MCP Site",
                identifiers=[{"type": "domain", "value": "example-mcp.com"}],
                tags=["mcp"],
                publisher_domain="example-mcp.com",
                verification_status="verified",
            )
            session.add(prop)
            session.commit()

        # Create mock FastMCP Context
        mock_context = Mock()
        mock_context.meta = {
            "headers": {
                "host": "test-mcp.example.com",
                "x-adcp-tenant": "test_tenant_mcp",
            }
        }

        # Execute - this is the code path that had the NameError bug
        # Before fix: NameError: name 'get_testing_context' is not defined
        # After fix: Works correctly
        req = ListAuthorizedPropertiesRequest()
        response = _list_authorized_properties_impl(req, mock_context)

        # Verify response
        assert isinstance(response, ListAuthorizedPropertiesResponse)
        assert "example-mcp.com" in response.publisher_domains
        assert response.errors == []

    def test_with_none_context(self, integration_db):
        """Test list_authorized_properties with None context (public discovery)."""
        # Create test tenant and property
        with get_db_session() as session:
            tenant = Tenant(
                tenant_id="test_tenant_none",
                name="Test Tenant None",
                subdomain="test-none",
            )
            session.add(tenant)
            session.flush()

            prop = AuthorizedProperty(
                property_id="prop_none_001",
                tenant_id=tenant.tenant_id,
                property_type="website",
                name="Test None Site",
                identifiers=[{"type": "domain", "value": "example-none.com"}],
                tags=["public"],
                publisher_domain="example-none.com",
                verification_status="verified",
            )
            session.add(prop)
            session.commit()

        # Set tenant context manually (simulates subdomain routing)
        from src.core.config_loader import set_current_tenant

        set_current_tenant(
            {
                "tenant_id": "test_tenant_none",
                "subdomain": "test-none",
                "advertising_policy": {},
            }
        )

        try:
            # Execute with None context
            req = ListAuthorizedPropertiesRequest()
            response = _list_authorized_properties_impl(req, None)

            # Verify response
            assert isinstance(response, ListAuthorizedPropertiesResponse)
            assert "example-none.com" in response.publisher_domains
            assert response.errors == []
        finally:
            # Clean up tenant context
            set_current_tenant(None)

    def test_import_get_testing_context(self):
        """Verify get_testing_context is properly imported.

        This test would have caught the NameError bug.
        """
        # Import should work without NameError
        from src.core.testing_hooks import AdCPTestContext, get_testing_context

        # Create mock context
        mock_context = Mock()
        mock_context.meta = {"headers": {}}

        # Call should work without NameError
        testing_ctx = get_testing_context(mock_context)

        # Verify it returns correct type
        assert isinstance(testing_ctx, AdCPTestContext)
        assert testing_ctx.dry_run is False
        assert testing_ctx.test_session_id is None

    def test_with_testing_headers(self, integration_db):
        """Test list_authorized_properties with AdCP testing headers."""
        # Create test tenant and property
        with get_db_session() as session:
            tenant = Tenant(
                tenant_id="test_tenant_headers",
                name="Test Tenant Headers",
                subdomain="test-headers",
            )
            session.add(tenant)
            session.flush()

            prop = AuthorizedProperty(
                property_id="prop_headers_001",
                tenant_id=tenant.tenant_id,
                property_type="website",
                name="Test Headers Site",
                identifiers=[{"type": "domain", "value": "example-headers.com"}],
                tags=["test"],
                publisher_domain="example-headers.com",
                verification_status="verified",
            )
            session.add(prop)
            session.commit()

        # Create mock FastMCP Context with testing headers
        mock_context = Mock()
        mock_context.meta = {
            "headers": {
                "host": "test-headers.example.com",
                "x-adcp-tenant": "test_tenant_headers",
                "x-dry-run": "true",
                "x-test-session-id": "test_session_123",
            }
        }

        # Execute with testing headers
        req = ListAuthorizedPropertiesRequest()
        response = _list_authorized_properties_impl(req, mock_context)

        # Verify response
        assert isinstance(response, ListAuthorizedPropertiesResponse)
        assert "example-headers.com" in response.publisher_domains
        assert response.errors == []
