"""
Unit tests for GAMAuthManager class.

Tests authentication credential management, OAuth and service account flows,
configuration validation, and error handling scenarios.
"""

import pytest

from src.adapters.gam.auth import GAMAuthManager


class TestGAMAuthManager:
    """Test suite for GAMAuthManager authentication functionality."""

    def test_init_with_refresh_token_config(self):
        """Test initialization with OAuth refresh token configuration."""
        config = {"refresh_token": "test_refresh_token"}

        auth_manager = GAMAuthManager(config)

        assert auth_manager.config == config
        assert auth_manager.refresh_token == "test_refresh_token"
        assert auth_manager.key_file is None

    def test_init_with_service_account_config(self):
        """Test initialization with service account key file configuration."""
        config = {"service_account_key_file": "/path/to/key.json"}

        auth_manager = GAMAuthManager(config)

        assert auth_manager.config == config
        assert auth_manager.refresh_token is None
        assert auth_manager.key_file == "/path/to/key.json"

    def test_init_with_both_auth_methods(self):
        """Test initialization with both authentication methods (refresh token takes precedence)."""
        config = {"refresh_token": "test_refresh_token", "service_account_key_file": "/path/to/key.json"}

        auth_manager = GAMAuthManager(config)

        assert auth_manager.refresh_token == "test_refresh_token"
        assert auth_manager.key_file == "/path/to/key.json"

    def test_init_with_no_auth_config_raises_error(self):
        """Test that initialization without authentication configuration raises ValueError."""
        config = {}

        with pytest.raises(
            ValueError, match="GAM config requires either 'refresh_token' or 'service_account_key_file'"
        ):
            GAMAuthManager(config)

    def test_init_with_empty_values_raises_error(self):
        """Test that initialization with empty auth values raises ValueError."""
        config = {"refresh_token": "", "service_account_key_file": ""}

        with pytest.raises(
            ValueError, match="GAM config requires either 'refresh_token' or 'service_account_key_file'"
        ):
            GAMAuthManager(config)

    def test_is_oauth_configured_true(self):
        """Test OAuth configuration detection when refresh token is present."""
        config = {"refresh_token": "test_refresh_token"}
        auth_manager = GAMAuthManager(config)

        assert auth_manager.is_oauth_configured() is True

    def test_is_oauth_configured_false(self):
        """Test OAuth configuration detection when refresh token is missing."""
        config = {"service_account_key_file": "/path/to/key.json"}
        auth_manager = GAMAuthManager(config)

        assert auth_manager.is_oauth_configured() is False

    def test_is_service_account_configured_true(self):
        """Test service account configuration detection when key file is present."""
        config = {"service_account_key_file": "/path/to/key.json"}
        auth_manager = GAMAuthManager(config)

        assert auth_manager.is_service_account_configured() is True

    def test_is_service_account_configured_false(self):
        """Test service account configuration detection when key file is missing."""
        config = {"refresh_token": "test_refresh_token"}
        auth_manager = GAMAuthManager(config)

        assert auth_manager.is_service_account_configured() is False

    def test_get_auth_method_oauth(self):
        """Test authentication method detection for OAuth."""
        config = {"refresh_token": "test_refresh_token"}
        auth_manager = GAMAuthManager(config)

        assert auth_manager.get_auth_method() == "oauth"

    def test_get_auth_method_service_account(self):
        """Test authentication method detection for service account."""
        config = {"service_account_key_file": "/path/to/key.json"}
        auth_manager = GAMAuthManager(config)

        assert auth_manager.get_auth_method() == "service_account"

    def test_get_auth_method_oauth_precedence(self):
        """Test that OAuth takes precedence when both methods are configured."""
        config = {"refresh_token": "test_refresh_token", "service_account_key_file": "/path/to/key.json"}
        auth_manager = GAMAuthManager(config)

        assert auth_manager.get_auth_method() == "oauth"

    def test_get_auth_method_none(self):
        """Test authentication method detection when no method is configured."""
        # Create with valid config then remove auth methods
        config = {"refresh_token": "test"}
        auth_manager = GAMAuthManager(config)
        auth_manager.refresh_token = None
        auth_manager.key_file = None

        assert auth_manager.get_auth_method() == "none"

    def test_get_credentials_no_valid_method_error(self):
        """Test error when no valid authentication method is configured."""
        # Create auth manager with config but then remove auth methods
        config = {"refresh_token": "test"}
        auth_manager = GAMAuthManager(config)
        auth_manager.refresh_token = None
        auth_manager.key_file = None

        with pytest.raises(ValueError, match="No valid authentication method configured"):
            auth_manager.get_credentials()

    def test_config_with_none_values(self):
        """Test handling of None values in configuration."""
        config = {"refresh_token": None, "service_account_key_file": None}

        with pytest.raises(
            ValueError, match="GAM config requires either 'refresh_token' or 'service_account_key_file'"
        ):
            GAMAuthManager(config)

    def test_config_with_whitespace_values(self):
        """Test handling of whitespace-only values in configuration."""
        config = {"refresh_token": "   ", "service_account_key_file": "\t\n"}
        # Whitespace values are considered valid by the implementation
        auth_manager = GAMAuthManager(config)
        assert auth_manager.refresh_token == "   "
        assert auth_manager.key_file == "\t\n"

    def test_unexpected_config_keys_ignored(self):
        """Test that unexpected configuration keys are safely ignored."""
        config = {"refresh_token": "test_token", "unexpected_key": "unexpected_value", "another_key": 12345}

        # Should not raise error and should work normally
        auth_manager = GAMAuthManager(config)
        assert auth_manager.is_oauth_configured() is True

    def test_config_modification_after_init(self):
        """Test that modifying config after initialization doesn't affect behavior."""
        config = {"refresh_token": "original_token"}
        auth_manager = GAMAuthManager(config)

        # Modify the original config
        config["refresh_token"] = "modified_token"
        config["service_account_key_file"] = "/new/path.json"

        # Auth manager should still use original values
        assert auth_manager.refresh_token == "original_token"
        assert auth_manager.key_file is None
        assert auth_manager.is_oauth_configured() is True
        assert auth_manager.get_auth_method() == "oauth"
