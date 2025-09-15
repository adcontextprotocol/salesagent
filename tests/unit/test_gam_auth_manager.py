"""
Unit tests for GAMAuthManager class.

Tests authentication credential management, OAuth and service account flows,
configuration validation, and error handling scenarios.
"""

from unittest.mock import Mock, patch

import pytest

from src.adapters.gam.auth import GAMAuthManager


class MockGAMOAuthConfig:
    """Mock GAM OAuth configuration for testing."""

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret


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

    @patch("src.adapters.gam.auth.get_gam_oauth_config")
    @patch("src.adapters.gam.auth.oauth2.GoogleRefreshTokenClient")
    def test_get_credentials_oauth_success(self, mock_oauth_client, mock_get_config):
        """Test successful OAuth credential creation."""
        # Setup mocks
        mock_config = MockGAMOAuthConfig("test_client_id", "test_client_secret")
        mock_get_config.return_value = mock_config
        mock_client_instance = Mock()
        mock_oauth_client.return_value = mock_client_instance

        config = {"refresh_token": "test_refresh_token"}
        auth_manager = GAMAuthManager(config)

        # Test credential creation
        credentials = auth_manager.get_credentials()

        # Verify OAuth client was created with correct parameters
        mock_oauth_client.assert_called_once_with(
            client_id="test_client_id", client_secret="test_client_secret", refresh_token="test_refresh_token"
        )
        assert credentials == mock_client_instance

    @patch("src.adapters.gam.auth.get_gam_oauth_config")
    def test_get_credentials_oauth_config_error(self, mock_get_config):
        """Test OAuth credential creation with configuration error."""
        # Mock configuration error
        mock_get_config.side_effect = Exception("OAuth config not found")

        config = {"refresh_token": "test_refresh_token"}
        auth_manager = GAMAuthManager(config)

        # Should raise ValueError with descriptive message
        with pytest.raises(ValueError, match="GAM OAuth configuration error: OAuth config not found"):
            auth_manager.get_credentials()

    @patch("src.adapters.gam.auth.google.oauth2.service_account.Credentials.from_service_account_file")
    def test_get_credentials_service_account_success(self, mock_from_file):
        """Test successful service account credential creation."""
        # Setup mock
        mock_credentials = Mock()
        mock_from_file.return_value = mock_credentials

        config = {"service_account_key_file": "/path/to/key.json"}
        auth_manager = GAMAuthManager(config)

        # Test credential creation
        credentials = auth_manager.get_credentials()

        # Verify service account credentials were created with correct parameters
        mock_from_file.assert_called_once_with("/path/to/key.json", scopes=["https://www.googleapis.com/auth/dfp"])
        assert credentials == mock_credentials

    @patch("src.adapters.gam.auth.google.oauth2.service_account.Credentials.from_service_account_file")
    def test_get_credentials_service_account_file_error(self, mock_from_file):
        """Test service account credential creation with file error."""
        # Mock file error
        mock_from_file.side_effect = FileNotFoundError("Key file not found")

        config = {"service_account_key_file": "/path/to/missing.json"}
        auth_manager = GAMAuthManager(config)

        # Should re-raise the original exception
        with pytest.raises(FileNotFoundError, match="Key file not found"):
            auth_manager.get_credentials()

    def test_get_credentials_no_valid_method_error(self):
        """Test error when no valid authentication method is configured."""
        # Create auth manager with config but then remove auth methods
        config = {"refresh_token": "test"}
        auth_manager = GAMAuthManager(config)
        auth_manager.refresh_token = None
        auth_manager.key_file = None

        with pytest.raises(ValueError, match="No valid authentication method configured"):
            auth_manager.get_credentials()

    @patch("src.adapters.gam.auth.get_gam_oauth_config")
    @patch("src.adapters.gam.auth.oauth2.GoogleRefreshTokenClient")
    def test_get_credentials_oauth_client_error(self, mock_oauth_client, mock_get_config):
        """Test OAuth credential creation with client creation error."""
        # Setup mocks
        mock_config = MockGAMOAuthConfig("test_client_id", "test_client_secret")
        mock_get_config.return_value = mock_config
        mock_oauth_client.side_effect = Exception("OAuth client creation failed")

        config = {"refresh_token": "test_refresh_token"}
        auth_manager = GAMAuthManager(config)

        # Should re-raise the OAuth client error
        with pytest.raises(Exception, match="OAuth client creation failed"):
            auth_manager.get_credentials()

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


class TestGAMAuthManagerIntegration:
    """Integration tests for GAMAuthManager with real-like scenarios."""

    def test_oauth_flow_end_to_end(self):
        """Test complete OAuth authentication flow with realistic configuration."""
        config = {
            "refresh_token": "1//test_refresh_token_example",
            "extra_field": "ignored",  # Extra config fields should be ignored
        }

        with (
            patch("src.adapters.gam.auth.get_gam_oauth_config") as mock_get_config,
            patch("src.adapters.gam.auth.oauth2.GoogleRefreshTokenClient") as mock_oauth_client,
        ):

            # Setup realistic config
            mock_config = MockGAMOAuthConfig("123456789.apps.googleusercontent.com", "gam_client_secret_example")
            mock_get_config.return_value = mock_config

            mock_client_instance = Mock()
            mock_oauth_client.return_value = mock_client_instance

            auth_manager = GAMAuthManager(config)

            # Test all methods work together
            assert auth_manager.is_oauth_configured() is True
            assert auth_manager.is_service_account_configured() is False
            assert auth_manager.get_auth_method() == "oauth"

            credentials = auth_manager.get_credentials()
            assert credentials == mock_client_instance

            # Verify OAuth client creation with realistic parameters
            mock_oauth_client.assert_called_once_with(
                client_id="123456789.apps.googleusercontent.com",
                client_secret="gam_client_secret_example",
                refresh_token="1//test_refresh_token_example",
            )

    def test_service_account_flow_end_to_end(self):
        """Test complete service account authentication flow."""
        config = {
            "service_account_key_file": "/var/secrets/gam-service-account.json",
            "network_code": "12345678",  # Extra config should be preserved
        }

        with patch(
            "src.adapters.gam.auth.google.oauth2.service_account.Credentials.from_service_account_file"
        ) as mock_from_file:
            mock_credentials = Mock()
            mock_from_file.return_value = mock_credentials

            auth_manager = GAMAuthManager(config)

            # Test all methods work together
            assert auth_manager.is_oauth_configured() is False
            assert auth_manager.is_service_account_configured() is True
            assert auth_manager.get_auth_method() == "service_account"

            credentials = auth_manager.get_credentials()
            assert credentials == mock_credentials

            # Verify service account creation with correct scope
            mock_from_file.assert_called_once_with(
                "/var/secrets/gam-service-account.json", scopes=["https://www.googleapis.com/auth/dfp"]
            )

    def test_error_handling_preserves_original_exceptions(self):
        """Test that error handling preserves original exception details."""
        config = {"service_account_key_file": "/nonexistent/path.json"}
        auth_manager = GAMAuthManager(config)

        with patch(
            "src.adapters.gam.auth.google.oauth2.service_account.Credentials.from_service_account_file"
        ) as mock_from_file:
            original_error = FileNotFoundError("No such file or directory: '/nonexistent/path.json'")
            mock_from_file.side_effect = original_error

            # Should preserve the original exception type and message
            with pytest.raises(FileNotFoundError) as exc_info:
                auth_manager.get_credentials()

            assert str(exc_info.value) == str(original_error)


class TestGAMAuthManagerEdgeCases:
    """Test edge cases and boundary conditions for GAMAuthManager."""

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

        with pytest.raises(
            ValueError, match="GAM config requires either 'refresh_token' or 'service_account_key_file'"
        ):
            GAMAuthManager(config)

    def test_unexpected_config_keys_ignored(self):
        """Test that unexpected configuration keys are safely ignored."""
        config = {"refresh_token": "test_token", "unexpected_key": "unexpected_value", "another_key": 12345}

        # Should not raise error and should work normally
        auth_manager = GAMAuthManager(config)
        assert auth_manager.is_oauth_configured() is True

    @patch("src.adapters.gam.auth.get_gam_oauth_config")
    def test_oauth_config_import_error_handling(self, mock_get_config):
        """Test handling of import errors when getting OAuth configuration."""
        mock_get_config.side_effect = ImportError("Cannot import config module")

        config = {"refresh_token": "test_refresh_token"}
        auth_manager = GAMAuthManager(config)

        with pytest.raises(ValueError, match="GAM OAuth configuration error: Cannot import config module"):
            auth_manager.get_credentials()

    def test_repeated_get_credentials_calls(self):
        """Test that multiple calls to get_credentials work correctly."""
        config = {"refresh_token": "test_refresh_token"}

        with (
            patch("src.adapters.gam.auth.get_gam_oauth_config") as mock_get_config,
            patch("src.adapters.gam.auth.oauth2.GoogleRefreshTokenClient") as mock_oauth_client,
        ):

            mock_config = MockGAMOAuthConfig("client_id", "client_secret")
            mock_get_config.return_value = mock_config
            mock_client_instance = Mock()
            mock_oauth_client.return_value = mock_client_instance

            auth_manager = GAMAuthManager(config)

            # Call get_credentials multiple times
            creds1 = auth_manager.get_credentials()
            creds2 = auth_manager.get_credentials()
            creds3 = auth_manager.get_credentials()

            # Should create new credentials each time (no caching)
            assert creds1 == mock_client_instance
            assert creds2 == mock_client_instance
            assert creds3 == mock_client_instance

            # Should call OAuth client creation multiple times
            assert mock_oauth_client.call_count == 3

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
