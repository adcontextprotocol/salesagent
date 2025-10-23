"""Unit test for tenant isolation fix in get_principal_from_token.

This test verifies that get_principal_from_token() preserves tenant context
when tenant_id is provided (from subdomain), and only sets tenant context
from the principal when doing global token lookup.
"""

from unittest.mock import MagicMock, patch


def test_get_principal_from_token_preserves_tenant_context_when_specified():
    """Test that get_principal_from_token preserves tenant context when tenant_id is provided."""
    from src.core.main import get_principal_from_token

    # Mock database session and queries
    with patch("src.core.main.get_db_session") as mock_get_db:
        mock_session = MagicMock()
        mock_get_db.return_value.__enter__.return_value = mock_session

        # Mock principal lookup - principal belongs to tenant_test_agent
        mock_principal = MagicMock()
        mock_principal.principal_id = "principal_test_agent"
        mock_principal.tenant_id = "tenant_test_agent"
        mock_principal.access_token = "test_token"

        # Mock the query to return the principal
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_principal
        mock_session.scalars.return_value = mock_scalars
        mock_session.begin.return_value.__enter__ = lambda self: None
        mock_session.begin.return_value.__exit__ = lambda self, *args: None

        # Mock tenant lookup for admin token check
        mock_tenant = MagicMock()
        mock_tenant.admin_token = "different_token"  # Not matching

        # Setup mock to return principal first, then tenant
        def scalars_side_effect(stmt):
            mock_result = MagicMock()
            # First call returns principal, subsequent calls return tenant
            if not hasattr(scalars_side_effect, "call_count"):
                scalars_side_effect.call_count = 0
            scalars_side_effect.call_count += 1

            if scalars_side_effect.call_count == 1:
                mock_result.first.return_value = mock_principal
            else:
                mock_result.first.return_value = mock_tenant
            return mock_result

        mock_session.scalars.side_effect = scalars_side_effect

        # Mock set_current_tenant to track calls
        with patch("src.core.main.set_current_tenant") as mock_set_tenant:
            # Call get_principal_from_token WITH tenant_id (subdomain case)
            result = get_principal_from_token("test_token", tenant_id="tenant_wonderstruck")

            # Verify principal was returned
            assert result == "principal_test_agent"

            # CRITICAL: Verify set_current_tenant was NOT called
            # When tenant_id is provided, the caller has already set the context
            # and we should NOT overwrite it
            mock_set_tenant.assert_not_called()


def test_get_principal_from_token_sets_tenant_context_for_global_lookup():
    """Test that get_principal_from_token sets tenant context when doing global lookup (no tenant_id)."""
    from src.core.main import get_principal_from_token

    # Mock database session and queries
    with patch("src.core.main.get_db_session") as mock_get_db:
        mock_session = MagicMock()
        mock_get_db.return_value.__enter__.return_value = mock_session

        # Mock principal
        mock_principal = MagicMock()
        mock_principal.principal_id = "principal_global"
        mock_principal.tenant_id = "tenant_global"
        mock_principal.access_token = "global_token"

        # Mock tenant
        mock_tenant = MagicMock()
        mock_tenant.tenant_id = "tenant_global"
        mock_tenant.admin_token = "different_token"

        # Setup mock to return principal, then tenant_check, then tenant
        def scalars_side_effect(stmt):
            mock_result = MagicMock()
            if not hasattr(scalars_side_effect, "call_count"):
                scalars_side_effect.call_count = 0
            scalars_side_effect.call_count += 1

            if scalars_side_effect.call_count == 1:
                # First call: principal lookup
                mock_result.first.return_value = mock_principal
            elif scalars_side_effect.call_count == 2:
                # Second call: tenant validation
                mock_result.first.return_value = mock_tenant
            else:
                # Third call: tenant for context setting
                mock_result.first.return_value = mock_tenant
            return mock_result

        mock_session.scalars.side_effect = scalars_side_effect
        mock_session.begin.return_value.__enter__ = lambda self: None
        mock_session.begin.return_value.__exit__ = lambda self, *args: None

        # Mock set_current_tenant and serialize_tenant_to_dict (imported inside function)
        with patch("src.core.main.set_current_tenant") as mock_set_tenant:
            with patch("src.core.utils.tenant_utils.serialize_tenant_to_dict") as mock_serialize:
                mock_serialize.return_value = {"tenant_id": "tenant_global", "subdomain": "global"}

                # Call get_principal_from_token WITHOUT tenant_id (global lookup)
                result = get_principal_from_token("global_token", tenant_id=None)

                # Verify principal was returned
                assert result == "principal_global"

                # CRITICAL: Verify set_current_tenant WAS called
                # For global lookup, we SHOULD set tenant context from principal
                mock_set_tenant.assert_called_once()
                call_args = mock_set_tenant.call_args[0][0]
                assert call_args["tenant_id"] == "tenant_global"


def test_get_principal_from_token_with_admin_token_and_tenant_id():
    """Test that admin token with tenant_id doesn't overwrite tenant context."""
    from src.core.main import get_principal_from_token

    with patch("src.core.main.get_db_session") as mock_get_db:
        mock_session = MagicMock()
        mock_get_db.return_value.__enter__.return_value = mock_session

        # Mock tenant with admin token
        mock_tenant = MagicMock()
        mock_tenant.tenant_id = "tenant_admin"
        mock_tenant.admin_token = "admin_token_123"

        # Setup mock: no principal found, then tenant with matching admin token
        def scalars_side_effect(stmt):
            mock_result = MagicMock()
            if not hasattr(scalars_side_effect, "call_count"):
                scalars_side_effect.call_count = 0
            scalars_side_effect.call_count += 1

            if scalars_side_effect.call_count == 1:
                # First call: principal lookup (not found)
                mock_result.first.return_value = None
            else:
                # Second call: tenant lookup for admin token check
                mock_result.first.return_value = mock_tenant
            return mock_result

        mock_session.scalars.side_effect = scalars_side_effect
        mock_session.begin.return_value.__enter__ = lambda self: None
        mock_session.begin.return_value.__exit__ = lambda self, *args: None

        with patch("src.core.main.set_current_tenant") as mock_set_tenant:
            with patch("src.core.utils.tenant_utils.serialize_tenant_to_dict") as mock_serialize:
                mock_serialize.return_value = {"tenant_id": "tenant_admin"}

                # Call with admin token and tenant_id
                result = get_principal_from_token("admin_token_123", tenant_id="tenant_admin")

                # Verify admin principal was returned
                assert result == "tenant_admin_admin"

                # Verify set_current_tenant was called exactly once (for admin token setup)
                assert mock_set_tenant.call_count == 1
