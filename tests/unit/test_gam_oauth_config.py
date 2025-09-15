"""Tests for GAM OAuth configuration management."""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.core.config import AppConfig, GAMOAuthConfig, get_config, validate_configuration


class TestGAMOAuthConfig:
    """Test GAM OAuth configuration class."""

    def test_valid_gam_oauth_config(self):
        """Test valid GAM OAuth configuration."""
        with patch.dict(
            os.environ,
            {
                "GAM_OAUTH_CLIENT_ID": "123456789-test.apps.googleusercontent.com",
                "GAM_OAUTH_CLIENT_SECRET": "GOCSPX-test_secret_key",
            },
        ):
            config = GAMOAuthConfig()
            assert config.client_id == "123456789-test.apps.googleusercontent.com"
            assert config.client_secret == "GOCSPX-test_secret_key"

    def test_invalid_client_id_format(self):
        """Test invalid client ID format."""
        with patch.dict(
            os.environ,
            {"GAM_OAUTH_CLIENT_ID": "invalid-client-id", "GAM_OAUTH_CLIENT_SECRET": "GOCSPX-test_secret_key"},
        ):
            with pytest.raises(ValidationError, match="must end with '.apps.googleusercontent.com'"):
                GAMOAuthConfig()

    def test_invalid_client_secret_format(self):
        """Test invalid client secret format."""
        with patch.dict(
            os.environ,
            {
                "GAM_OAUTH_CLIENT_ID": "123456789-test.apps.googleusercontent.com",
                "GAM_OAUTH_CLIENT_SECRET": "invalid-secret",
            },
        ):
            with pytest.raises(ValidationError, match="must start with 'GOCSPX-'"):
                GAMOAuthConfig()

    def test_empty_client_id(self):
        """Test empty client ID."""
        with patch.dict(os.environ, {"GAM_OAUTH_CLIENT_ID": "", "GAM_OAUTH_CLIENT_SECRET": "GOCSPX-test_secret_key"}):
            with pytest.raises(ValidationError, match="GAM OAuth Client ID cannot be empty"):
                GAMOAuthConfig()

    def test_empty_client_secret(self):
        """Test empty client secret."""
        with patch.dict(
            os.environ,
            {"GAM_OAUTH_CLIENT_ID": "123456789-test.apps.googleusercontent.com", "GAM_OAUTH_CLIENT_SECRET": ""},
        ):
            with pytest.raises(ValidationError, match="GAM OAuth Client Secret cannot be empty"):
                GAMOAuthConfig()

    def test_missing_environment_variables(self):
        """Test missing environment variables."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValidationError):
                GAMOAuthConfig()


class TestAppConfig:
    """Test main application configuration."""

    @patch.dict(
        os.environ,
        {
            "GEMINI_API_KEY": "test-gemini-key",
            "SUPER_ADMIN_EMAILS": "admin@example.com,user@example.com",
            "GAM_OAUTH_CLIENT_ID": "123456789-test.apps.googleusercontent.com",
            "GAM_OAUTH_CLIENT_SECRET": "GOCSPX-test_secret_key",
            "DATABASE_URL": "postgresql://test:test@localhost/test",
        },
    )
    def test_complete_app_config(self):
        """Test complete application configuration."""
        config = AppConfig()

        assert config.gemini_api_key == "test-gemini-key"
        assert config.superadmin.emails == "admin@example.com,user@example.com"
        assert config.superadmin.email_list == ["admin@example.com", "user@example.com"]
        assert config.gam_oauth.client_id == "123456789-test.apps.googleusercontent.com"
        assert config.gam_oauth.client_secret == "GOCSPX-test_secret_key"
        assert config.database.url == "postgresql://test:test@localhost/test"

    @patch.dict(os.environ, {"SUPER_ADMIN_DOMAINS": "example.com,test.com"})
    def test_superadmin_domain_list(self):
        """Test superadmin domain list parsing."""
        # Need to set required fields for config to validate
        with patch.dict(
            os.environ,
            {
                "GEMINI_API_KEY": "test-key",
                "SUPER_ADMIN_EMAILS": "admin@example.com",
                "GAM_OAUTH_CLIENT_ID": "123456789-test.apps.googleusercontent.com",
                "GAM_OAUTH_CLIENT_SECRET": "GOCSPX-test_secret_key",
                "DATABASE_URL": "postgresql://test:test@localhost/test",
                "SUPER_ADMIN_DOMAINS": "example.com,test.com",
            },
        ):
            config = AppConfig()
            assert config.superadmin.domain_list == ["example.com", "test.com"]


class TestConfigurationValidation:
    """Test configuration validation."""

    @patch.dict(
        os.environ,
        {
            "GEMINI_API_KEY": "test-gemini-key",
            "SUPER_ADMIN_EMAILS": "admin@example.com",
            "GAM_OAUTH_CLIENT_ID": "123456789-test.apps.googleusercontent.com",
            "GAM_OAUTH_CLIENT_SECRET": "GOCSPX-test_secret_key",
            "DATABASE_URL": "postgresql://test:test@localhost/test",
        },
    )
    def test_successful_validation(self):
        """Test successful configuration validation."""
        # Should not raise any exceptions
        validate_configuration()

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_required_config(self):
        """Test validation with missing required configuration."""
        # Clear the global config singleton to ensure clean test state
        import src.core.config

        src.core.config._config = None

        with pytest.raises(RuntimeError, match="Configuration validation failed"):
            validate_configuration()

    @patch.dict(
        os.environ,
        {
            "GEMINI_API_KEY": "test-key",
            "SUPER_ADMIN_EMAILS": "admin@example.com",
            "GAM_OAUTH_CLIENT_ID": "invalid-client-id",
            "GAM_OAUTH_CLIENT_SECRET": "GOCSPX-test_secret_key",
        },
    )
    def test_invalid_gam_config_validation(self):
        """Test validation with invalid GAM OAuth configuration."""
        # Clear the global config singleton to ensure clean test state
        import src.core.config

        src.core.config._config = None

        with pytest.raises(RuntimeError, match="Configuration validation failed"):
            validate_configuration()


class TestConfigSingleton:
    """Test configuration singleton behavior."""

    @patch.dict(
        os.environ,
        {
            "GEMINI_API_KEY": "test-gemini-key",
            "SUPER_ADMIN_EMAILS": "admin@example.com",
            "GAM_OAUTH_CLIENT_ID": "123456789-test.apps.googleusercontent.com",
            "GAM_OAUTH_CLIENT_SECRET": "GOCSPX-test_secret_key",
            "DATABASE_URL": "postgresql://test:test@localhost/test",
        },
    )
    def test_config_singleton(self):
        """Test that get_config returns the same instance."""
        # Clear any existing config
        import src.core.config

        src.core.config._config = None

        config1 = get_config()
        config2 = get_config()

        assert config1 is config2
        assert config1.gemini_api_key == "test-gemini-key"
