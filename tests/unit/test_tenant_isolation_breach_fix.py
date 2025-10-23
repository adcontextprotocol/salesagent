"""Unit tests for tenant isolation breach fix.

These tests verify the security fixes work without requiring a database:

1. get_current_tenant() now raises RuntimeError instead of falling back to default tenant
2. get_principal_from_context() now raises ToolError if tenant cannot be determined from headers
3. Global token lookup is prevented when tenant detection fails

Bug Report:
- User called wonderstruck endpoint with valid token
- Got back products from test-agent tenant
- Root cause: Tenant detection failed, fell back to global token lookup, which found test-agent principal

Security Fixes:
1. Removed dangerous fallback in get_current_tenant() that returned first active tenant
2. Added tenant detection requirement - reject requests if tenant can't be determined
3. Fail loudly with clear error messages instead of silently using wrong tenant
"""

from unittest.mock import Mock, patch

import pytest
from fastmcp.exceptions import ToolError


def test_get_current_tenant_fails_without_context():
    """Test that get_current_tenant() raises error instead of falling back."""
    from src.core.config_loader import current_tenant, get_current_tenant

    # Clear any existing tenant context
    current_tenant.set(None)

    # Should raise RuntimeError, not return a default tenant
    with pytest.raises(RuntimeError) as exc_info:
        get_current_tenant()

    error_msg = str(exc_info.value)
    assert "No tenant context set" in error_msg
    assert "security error" in error_msg.lower()
    assert "breach tenant isolation" in error_msg.lower()


def test_get_principal_from_context_rejects_when_no_tenant_detected():
    """Test that authentication fails if tenant cannot be determined from headers."""
    from src.core.main import get_principal_from_context

    # Create mock context with auth token but no tenant detection possible
    context = Mock()
    context.meta = {
        "headers": {
            "x-adcp-auth": "some-valid-token",
            "host": "localhost",  # Not a valid subdomain for tenant detection
        }
    }

    # Mock get_http_headers to return empty dict (forcing fallback to context.meta)
    with patch("src.core.main.get_http_headers", return_value={}):
        # Should raise ToolError because tenant cannot be determined
        with pytest.raises(ToolError) as exc_info:
            get_principal_from_context(context)

        error = exc_info.value
        assert error.args[0] == "TENANT_DETECTION_FAILED"
        assert "Cannot determine tenant" in error.args[1]
