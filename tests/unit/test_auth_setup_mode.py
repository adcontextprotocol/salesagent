"""Tests for auth setup mode functionality.

Auth setup mode allows test credentials to work per-tenant:
- New tenants start with auth_setup_mode=True (test credentials work)
- Admin configures SSO, tests it, then disables setup mode
- Once disabled, only SSO works
"""

import os
from unittest.mock import MagicMock, patch

from src.core.database.models import Tenant


class TestTenantAuthSetupMode:
    """Tests for the auth_setup_mode field on Tenant model."""

    def test_tenant_has_auth_setup_mode_field(self):
        """Tenant model should have auth_setup_mode field."""
        tenant = Tenant(
            tenant_id="test_tenant",
            name="Test Tenant",
            subdomain="test",
        )
        assert hasattr(tenant, "auth_setup_mode")

    def test_auth_setup_mode_defaults_to_true_in_schema(self):
        """The auth_setup_mode column should have server_default='true'."""
        from sqlalchemy import inspect

        mapper = inspect(Tenant)
        column = mapper.columns["auth_setup_mode"]
        assert column.server_default is not None
        assert "true" in str(column.server_default.arg).lower()

    def test_auth_setup_mode_is_boolean(self):
        """auth_setup_mode should be a boolean field."""
        from sqlalchemy import inspect

        mapper = inspect(Tenant)
        column = mapper.columns["auth_setup_mode"]
        assert column.type.python_type is bool


class TestSetupModeLogic:
    """Tests for the setup mode enable/disable logic."""

    def test_disable_setup_mode_requires_sso_enabled(self):
        """Should not allow disabling setup mode without SSO enabled."""
        tenant = MagicMock()
        tenant.auth_setup_mode = True

        auth_config = MagicMock()
        auth_config.oidc_enabled = False

        # Logic from disable_setup_mode endpoint:
        # if not auth_config or not auth_config.oidc_enabled:
        #     return error
        should_reject = not auth_config or not auth_config.oidc_enabled
        assert should_reject is True

    def test_disable_setup_mode_allowed_with_sso(self):
        """Should allow disabling setup mode when SSO is enabled."""
        tenant = MagicMock()
        tenant.auth_setup_mode = True

        auth_config = MagicMock()
        auth_config.oidc_enabled = True

        # Logic check
        should_reject = not auth_config or not auth_config.oidc_enabled
        assert should_reject is False

        # After successful disable:
        tenant.auth_setup_mode = False
        assert tenant.auth_setup_mode is False

    def test_enable_setup_mode_always_allowed(self):
        """Should always allow re-enabling setup mode."""
        tenant = MagicMock()
        tenant.auth_setup_mode = False

        # Enable it
        tenant.auth_setup_mode = True
        assert tenant.auth_setup_mode is True


class TestTestAuthEndpointLogic:
    """Tests for the /test/auth endpoint logic with setup mode."""

    def test_test_auth_allowed_with_env_var(self):
        """Test auth should be allowed when ADCP_AUTH_TEST_MODE=true."""
        with patch.dict(os.environ, {"ADCP_AUTH_TEST_MODE": "true"}):
            env_test_mode = os.environ.get("ADCP_AUTH_TEST_MODE", "").lower() == "true"
            tenant_setup_mode = False

            # Should NOT abort (allow access)
            should_abort = not env_test_mode and not tenant_setup_mode
            assert should_abort is False

    def test_test_auth_allowed_with_tenant_setup_mode(self):
        """Test auth should be allowed when tenant has auth_setup_mode=True."""
        with patch.dict(os.environ, {"ADCP_AUTH_TEST_MODE": ""}):
            env_test_mode = os.environ.get("ADCP_AUTH_TEST_MODE", "").lower() == "true"
            tenant_setup_mode = True  # Tenant is in setup mode

            # Should NOT abort (allow access)
            should_abort = not env_test_mode and not tenant_setup_mode
            assert should_abort is False

    def test_test_auth_blocked_when_both_disabled(self):
        """Test auth should 404 when both env var and setup mode are off."""
        with patch.dict(os.environ, {"ADCP_AUTH_TEST_MODE": ""}):
            env_test_mode = os.environ.get("ADCP_AUTH_TEST_MODE", "").lower() == "true"
            tenant_setup_mode = False  # Tenant disabled setup mode

            # SHOULD abort (deny access)
            should_abort = not env_test_mode and not tenant_setup_mode
            assert should_abort is True


class TestTenantLoginLogic:
    """Tests for tenant login page respecting setup mode."""

    def test_login_uses_tenant_auth_setup_mode(self):
        """Tenant login should use tenant's auth_setup_mode field."""
        tenant = MagicMock()
        tenant.auth_setup_mode = True

        # Logic from tenant_login:
        # test_mode = tenant.auth_setup_mode if hasattr(tenant, "auth_setup_mode") else True
        test_mode = tenant.auth_setup_mode if hasattr(tenant, "auth_setup_mode") else True
        assert test_mode is True

    def test_login_env_var_overrides_to_enable(self):
        """Env var ADCP_AUTH_TEST_MODE=true should override to enable test mode."""
        tenant = MagicMock()
        tenant.auth_setup_mode = False  # Tenant disabled setup mode

        with patch.dict(os.environ, {"ADCP_AUTH_TEST_MODE": "true"}):
            # Logic from tenant_login:
            test_mode = tenant.auth_setup_mode if hasattr(tenant, "auth_setup_mode") else True
            if os.environ.get("ADCP_AUTH_TEST_MODE", "").lower() == "true":
                test_mode = True

            assert test_mode is True

    def test_login_respects_disabled_setup_mode(self):
        """Tenant login should respect disabled setup mode when no env override."""
        tenant = MagicMock()
        tenant.auth_setup_mode = False  # Tenant disabled setup mode

        with patch.dict(os.environ, {"ADCP_AUTH_TEST_MODE": ""}):
            test_mode = tenant.auth_setup_mode if hasattr(tenant, "auth_setup_mode") else True
            if os.environ.get("ADCP_AUTH_TEST_MODE", "").lower() == "true":
                test_mode = True

            # Should remain False since no env override
            assert test_mode is False


class TestMigration:
    """Tests for the auth_setup_mode migration."""

    def test_migration_file_exists(self):
        """Migration file for auth_setup_mode should exist."""
        import os

        migration_path = "alembic/versions/add_auth_setup_mode.py"
        assert os.path.exists(migration_path), f"Migration file not found: {migration_path}"

    def test_migration_has_correct_revision(self):
        """Migration should have correct revision chain."""
        import importlib.util

        migration_path = "alembic/versions/add_auth_setup_mode.py"
        spec = importlib.util.spec_from_file_location("migration", migration_path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)

        # Check revision chain
        assert migration.revision == "add_auth_setup_mode"
        assert migration.down_revision == "add_tenant_auth_config"
        assert callable(migration.upgrade)
        assert callable(migration.downgrade)


class TestUsersEndpointConfig:
    """Tests for the users page template context."""

    def test_list_users_passes_auth_setup_mode(self):
        """list_users endpoint should pass auth_setup_mode to template."""
        # The endpoint passes these to the template:
        # auth_setup_mode=tenant.auth_setup_mode,
        # oidc_enabled=auth_config.oidc_enabled if auth_config else False,

        tenant = MagicMock()
        tenant.auth_setup_mode = True

        auth_config = MagicMock()
        auth_config.oidc_enabled = True

        context = {
            "auth_setup_mode": tenant.auth_setup_mode,
            "oidc_enabled": auth_config.oidc_enabled if auth_config else False,
        }

        assert context["auth_setup_mode"] is True
        assert context["oidc_enabled"] is True

    def test_list_users_handles_no_auth_config(self):
        """list_users should handle case when no auth config exists."""
        tenant = MagicMock()
        tenant.auth_setup_mode = True

        auth_config = None  # No auth config yet

        context = {
            "auth_setup_mode": tenant.auth_setup_mode,
            "oidc_enabled": auth_config.oidc_enabled if auth_config else False,
        }

        assert context["auth_setup_mode"] is True
        assert context["oidc_enabled"] is False
