"""
Unit tests for GAMClientManager class.

Tests client initialization, service access, health checking functionality,
connection management, and error handling scenarios.
"""

from unittest.mock import Mock, patch

import pytest

from src.adapters.gam.auth import GAMAuthManager
from src.adapters.gam.client import GAMClientManager
from src.adapters.gam.utils.health_check import HealthCheckResult, HealthStatus


class TestGAMClientManager:
    """Test suite for GAMClientManager client lifecycle management."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = {"refresh_token": "test_refresh_token", "network_code": "12345678"}
        self.network_code = "12345678"

    def test_init_with_valid_config(self):
        """Test initialization with valid configuration."""
        client_manager = GAMClientManager(self.config, self.network_code)

        assert client_manager.config == self.config
        assert client_manager.network_code == self.network_code
        assert isinstance(client_manager.auth_manager, GAMAuthManager)
        assert client_manager._client is None
        assert client_manager._health_checker is None

    def test_init_creates_auth_manager(self):
        """Test that initialization creates GAMAuthManager with correct config."""
        with patch("src.adapters.gam.client.GAMAuthManager") as mock_auth_manager:
            mock_auth_instance = Mock()
            mock_auth_manager.return_value = mock_auth_instance

            client_manager = GAMClientManager(self.config, self.network_code)

            mock_auth_manager.assert_called_once_with(self.config)
            assert client_manager.auth_manager == mock_auth_instance

    @patch("src.adapters.gam.client.ad_manager.AdManagerClient")
    def test_get_client_initializes_on_first_call(self, mock_ad_manager_client):
        """Test that get_client initializes client on first call."""
        mock_client_instance = Mock()
        mock_ad_manager_client.return_value = mock_client_instance

        with patch("src.adapters.gam.client.GAMAuthManager") as mock_auth_manager:
            mock_auth_instance = Mock()
            mock_credentials = Mock()
            mock_auth_instance.get_credentials.return_value = mock_credentials
            mock_auth_instance.get_auth_method.return_value = "oauth"
            mock_auth_manager.return_value = mock_auth_instance

            client_manager = GAMClientManager(self.config, self.network_code)

            # First call should initialize client
            client = client_manager.get_client()

            mock_ad_manager_client.assert_called_once_with(
                mock_credentials, "AdCP Sales Agent", network_code=self.network_code
            )
            assert client == mock_client_instance
            assert client_manager._client == mock_client_instance

    @patch("src.adapters.gam.client.ad_manager.AdManagerClient")
    def test_get_client_returns_cached_instance(self, mock_ad_manager_client):
        """Test that get_client returns cached instance on subsequent calls."""
        mock_client_instance = Mock()
        mock_ad_manager_client.return_value = mock_client_instance

        with patch("src.adapters.gam.client.GAMAuthManager") as mock_auth_manager:
            mock_auth_instance = Mock()
            mock_credentials = Mock()
            mock_auth_instance.get_credentials.return_value = mock_credentials
            mock_auth_instance.get_auth_method.return_value = "oauth"
            mock_auth_manager.return_value = mock_auth_instance

            client_manager = GAMClientManager(self.config, self.network_code)

            # First call initializes
            client1 = client_manager.get_client()
            # Second call should return cached instance
            client2 = client_manager.get_client()

            # Should only initialize once
            mock_ad_manager_client.assert_called_once()
            assert client1 == client2
            assert client1 == mock_client_instance

    def test_init_client_missing_network_code_raises_error(self):
        """Test that initialization without network code raises ValueError."""
        client_manager = GAMClientManager(self.config, "")

        with pytest.raises(ValueError, match="Network code is required for GAM client initialization"):
            client_manager._init_client()

    def test_init_client_none_network_code_raises_error(self):
        """Test that initialization with None network code raises ValueError."""
        client_manager = GAMClientManager(self.config, None)

        with pytest.raises(ValueError, match="Network code is required for GAM client initialization"):
            client_manager._init_client()

    @patch("src.adapters.gam.client.ad_manager.AdManagerClient")
    def test_init_client_auth_error_propagates(self, mock_ad_manager_client):
        """Test that authentication errors during client initialization are propagated."""
        with patch("src.adapters.gam.client.GAMAuthManager") as mock_auth_manager:
            mock_auth_instance = Mock()
            mock_auth_instance.get_credentials.side_effect = Exception("Auth failed")
            mock_auth_manager.return_value = mock_auth_instance

            client_manager = GAMClientManager(self.config, self.network_code)

            with pytest.raises(Exception, match="Auth failed"):
                client_manager._init_client()

    @patch("src.adapters.gam.client.ad_manager.AdManagerClient")
    def test_init_client_ad_manager_error_propagates(self, mock_ad_manager_client):
        """Test that AdManager client creation errors are propagated."""
        mock_ad_manager_client.side_effect = Exception("AdManager client failed")

        with patch("src.adapters.gam.client.GAMAuthManager") as mock_auth_manager:
            mock_auth_instance = Mock()
            mock_credentials = Mock()
            mock_auth_instance.get_credentials.return_value = mock_credentials
            mock_auth_manager.return_value = mock_auth_instance

            client_manager = GAMClientManager(self.config, self.network_code)

            with pytest.raises(Exception, match="AdManager client failed"):
                client_manager._init_client()

    def test_get_service_calls_get_client(self):
        """Test that get_service properly calls get_client and GetService."""
        mock_client = Mock()
        mock_service = Mock()
        mock_client.GetService.return_value = mock_service

        client_manager = GAMClientManager(self.config, self.network_code)
        client_manager._client = mock_client  # Set cached client

        service = client_manager.get_service("OrderService")

        mock_client.GetService.assert_called_once_with("OrderService", version="v202411")
        assert service == mock_service

    def test_get_statement_builder_calls_get_client(self):
        """Test that get_statement_builder properly calls get_client and GetService."""
        mock_client = Mock()
        mock_statement_builder = Mock()
        mock_client.GetService.return_value = mock_statement_builder

        client_manager = GAMClientManager(self.config, self.network_code)
        client_manager._client = mock_client  # Set cached client

        statement_builder = client_manager.get_statement_builder()

        mock_client.GetService.assert_called_once_with("StatementBuilder", version="v202411")
        assert statement_builder == mock_statement_builder

    def test_is_connected_success(self):
        """Test is_connected returns True when connection test succeeds."""
        mock_client = Mock()
        mock_network_service = Mock()
        mock_network_service.getCurrentNetwork.return_value = {"id": "12345678"}
        mock_client.GetService.return_value = mock_network_service

        client_manager = GAMClientManager(self.config, self.network_code)
        client_manager._client = mock_client  # Set cached client

        assert client_manager.is_connected() is True
        mock_client.GetService.assert_called_once_with("NetworkService", version="v202411")
        mock_network_service.getCurrentNetwork.assert_called_once()

    def test_is_connected_failure(self):
        """Test is_connected returns False when connection test fails."""
        mock_client = Mock()
        mock_network_service = Mock()
        mock_network_service.getCurrentNetwork.side_effect = Exception("Connection failed")
        mock_client.GetService.return_value = mock_network_service

        client_manager = GAMClientManager(self.config, self.network_code)
        client_manager._client = mock_client  # Set cached client

        assert client_manager.is_connected() is False

    def test_reset_client_clears_cached_instance(self):
        """Test that reset_client clears the cached client instance."""
        mock_client = Mock()
        client_manager = GAMClientManager(self.config, self.network_code)
        client_manager._client = mock_client  # Set cached client

        client_manager.reset_client()

        assert client_manager._client is None

    @patch("src.adapters.gam.client.GAMHealthChecker")
    def test_get_health_checker_initializes_on_first_call(self, mock_health_checker_class):
        """Test that get_health_checker initializes health checker on first call."""
        mock_health_checker = Mock()
        mock_health_checker_class.return_value = mock_health_checker

        client_manager = GAMClientManager(self.config, self.network_code)

        health_checker = client_manager.get_health_checker(dry_run=True)

        mock_health_checker_class.assert_called_once_with(self.config, dry_run=True)
        assert health_checker == mock_health_checker
        assert client_manager._health_checker == mock_health_checker

    @patch("src.adapters.gam.client.GAMHealthChecker")
    def test_get_health_checker_returns_cached_instance(self, mock_health_checker_class):
        """Test that get_health_checker returns cached instance on subsequent calls."""
        mock_health_checker = Mock()
        mock_health_checker_class.return_value = mock_health_checker

        client_manager = GAMClientManager(self.config, self.network_code)

        # First call initializes
        health_checker1 = client_manager.get_health_checker()
        # Second call should return cached instance
        health_checker2 = client_manager.get_health_checker(dry_run=True)  # Different params ignored

        # Should only initialize once (with first call's parameters)
        mock_health_checker_class.assert_called_once_with(self.config, dry_run=False)
        assert health_checker1 == health_checker2

    def test_check_health_delegates_to_health_checker(self):
        """Test that check_health properly delegates to health checker."""
        mock_health_checker = Mock()
        mock_result = (HealthStatus.HEALTHY, [])
        mock_health_checker.run_all_checks.return_value = mock_result

        client_manager = GAMClientManager(self.config, self.network_code)
        client_manager._health_checker = mock_health_checker

        result = client_manager.check_health(advertiser_id="123", ad_unit_ids=["456", "789"])

        mock_health_checker.run_all_checks.assert_called_once_with(advertiser_id="123", ad_unit_ids=["456", "789"])
        assert result == mock_result

    def test_get_health_status_delegates_to_health_checker(self):
        """Test that get_health_status properly delegates to health checker."""
        mock_health_checker = Mock()
        mock_status = {"status": "healthy", "checks": []}
        mock_health_checker.get_status_summary.return_value = mock_status

        client_manager = GAMClientManager(self.config, self.network_code)
        client_manager._health_checker = mock_health_checker

        status = client_manager.get_health_status()

        mock_health_checker.get_status_summary.assert_called_once()
        assert status == mock_status

    def test_test_connection_delegates_to_health_checker(self):
        """Test that test_connection properly delegates to health checker."""
        mock_health_checker = Mock()
        mock_result = HealthCheckResult("auth", True, "Connection successful")
        mock_health_checker.check_authentication.return_value = mock_result

        client_manager = GAMClientManager(self.config, self.network_code)
        client_manager._health_checker = mock_health_checker

        result = client_manager.test_connection()

        mock_health_checker.check_authentication.assert_called_once()
        assert result == mock_result

    def test_test_permissions_delegates_to_health_checker(self):
        """Test that test_permissions properly delegates to health checker."""
        mock_health_checker = Mock()
        mock_result = HealthCheckResult("permissions", True, "Permissions valid")
        mock_health_checker.check_permissions.return_value = mock_result

        client_manager = GAMClientManager(self.config, self.network_code)
        client_manager._health_checker = mock_health_checker

        result = client_manager.test_permissions("advertiser_123")

        mock_health_checker.check_permissions.assert_called_once_with("advertiser_123")
        assert result == mock_result


class TestGAMClientManagerFromExistingClient:
    """Test suite for creating GAMClientManager from existing client."""

    def test_from_existing_client_creates_manager(self):
        """Test creating GAMClientManager from existing AdManagerClient."""
        mock_client = Mock()
        mock_client.network_code = "87654321"

        client_manager = GAMClientManager.from_existing_client(mock_client)

        assert client_manager.config == {"existing_client": True}
        assert client_manager.network_code == "87654321"
        assert client_manager.auth_manager is None
        assert client_manager._client == mock_client
        assert client_manager._health_checker is None

    def test_from_existing_client_missing_network_code(self):
        """Test creating from client without network_code attribute."""
        mock_client = Mock()
        del mock_client.network_code  # Remove network_code attribute

        client_manager = GAMClientManager.from_existing_client(mock_client)

        assert client_manager.network_code == "unknown"
        assert client_manager._client == mock_client

    def test_from_existing_client_get_client_returns_existing(self):
        """Test that get_client returns the existing client without re-initialization."""
        mock_client = Mock()
        mock_client.network_code = "87654321"

        client_manager = GAMClientManager.from_existing_client(mock_client)

        # Should return existing client without calling _init_client
        client = client_manager.get_client()
        assert client == mock_client

    def test_from_existing_client_services_work_normally(self):
        """Test that service access works normally with existing client."""
        mock_client = Mock()
        mock_client.network_code = "87654321"
        mock_service = Mock()
        mock_client.GetService.return_value = mock_service

        client_manager = GAMClientManager.from_existing_client(mock_client)

        service = client_manager.get_service("LineItemService")

        mock_client.GetService.assert_called_once_with("LineItemService", version="v202411")
        assert service == mock_service

    def test_from_existing_client_health_checks_work(self):
        """Test that health checking works with existing client."""
        mock_client = Mock()
        mock_client.network_code = "87654321"

        with patch("src.adapters.gam.client.GAMHealthChecker") as mock_health_checker_class:
            mock_health_checker = Mock()
            mock_health_checker_class.return_value = mock_health_checker

            client_manager = GAMClientManager.from_existing_client(mock_client)

            health_checker = client_manager.get_health_checker()

            # Should create health checker with existing client config
            mock_health_checker_class.assert_called_once_with({"existing_client": True}, dry_run=False)
            assert health_checker == mock_health_checker


class TestGAMClientManagerErrorHandling:
    """Test error handling scenarios for GAMClientManager."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = {"refresh_token": "test_token"}
        self.network_code = "12345678"

    def test_get_client_with_auth_failure(self):
        """Test get_client behavior when authentication fails."""
        with patch("src.adapters.gam.client.GAMAuthManager") as mock_auth_manager:
            mock_auth_instance = Mock()
            mock_auth_instance.get_credentials.side_effect = Exception("Auth failed")
            mock_auth_manager.return_value = mock_auth_instance

            client_manager = GAMClientManager(self.config, self.network_code)

            with pytest.raises(Exception, match="Auth failed"):
                client_manager.get_client()

    def test_get_service_with_client_failure(self):
        """Test get_service behavior when client initialization fails."""
        client_manager = GAMClientManager(self.config, self.network_code)

        with patch.object(client_manager, "get_client") as mock_get_client:
            mock_get_client.side_effect = Exception("Client init failed")

            with pytest.raises(Exception, match="Client init failed"):
                client_manager.get_service("OrderService")

    def test_is_connected_with_get_client_failure(self):
        """Test is_connected behavior when get_client fails."""
        client_manager = GAMClientManager(self.config, self.network_code)

        with patch.object(client_manager, "get_client") as mock_get_client:
            mock_get_client.side_effect = Exception("Client init failed")

            # Should return False instead of raising exception
            assert client_manager.is_connected() is False

    def test_health_checker_creation_failure(self):
        """Test behavior when health checker creation fails."""
        client_manager = GAMClientManager(self.config, self.network_code)

        with patch("src.adapters.gam.client.GAMHealthChecker") as mock_health_checker_class:
            mock_health_checker_class.side_effect = Exception("Health checker init failed")

            with pytest.raises(Exception, match="Health checker init failed"):
                client_manager.get_health_checker()

    def test_health_check_with_no_health_checker(self):
        """Test health check methods when health checker is None."""
        client_manager = GAMClientManager(self.config, self.network_code)

        with patch.object(client_manager, "get_health_checker") as mock_get_health_checker:
            mock_health_checker = Mock()
            mock_get_health_checker.return_value = mock_health_checker

            # Should create health checker and delegate
            client_manager.check_health()

            mock_get_health_checker.assert_called_once()
            mock_health_checker.run_all_checks.assert_called_once()


class TestGAMClientManagerEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_config(self):
        """Test initialization with empty config."""
        # Empty config should still work for client manager (auth manager will validate)
        client_manager = GAMClientManager({}, "12345678")

        assert client_manager.config == {}
        assert client_manager.network_code == "12345678"

    def test_config_modification_after_init(self):
        """Test that modifying config after initialization doesn't affect behavior."""
        config = {"refresh_token": "original_token"}
        client_manager = GAMClientManager(config, "12345678")

        # Modify original config
        config["refresh_token"] = "modified_token"
        config["new_field"] = "new_value"

        # Client manager should preserve original config reference
        assert client_manager.config["refresh_token"] == "modified_token"  # References same dict
        assert client_manager.network_code == "12345678"

    def test_multiple_reset_client_calls(self):
        """Test that multiple reset_client calls are safe."""
        client_manager = GAMClientManager({"refresh_token": "test"}, "12345678")

        # Multiple resets should be safe
        client_manager.reset_client()
        client_manager.reset_client()
        client_manager.reset_client()

        assert client_manager._client is None

    def test_get_service_with_special_characters(self):
        """Test get_service with service names containing special characters."""
        mock_client = Mock()
        mock_service = Mock()
        mock_client.GetService.return_value = mock_service

        client_manager = GAMClientManager({"refresh_token": "test"}, "12345678")
        client_manager._client = mock_client

        # Should handle service names with special characters
        service = client_manager.get_service("Custom.Service-Name_123")

        mock_client.GetService.assert_called_once_with("Custom.Service-Name_123", version="v202411")
        assert service == mock_service

    def test_network_code_types(self):
        """Test that network code handles different data types correctly."""
        # String network code (normal case)
        client_manager = GAMClientManager({"refresh_token": "test"}, "12345678")
        assert client_manager.network_code == "12345678"

        # Integer network code (should be converted to string for AdManager API)
        client_manager = GAMClientManager({"refresh_token": "test"}, 87654321)
        assert client_manager.network_code == 87654321

    @patch("src.adapters.gam.client.ad_manager.AdManagerClient")
    def test_client_initialization_with_different_auth_methods(self, mock_ad_manager_client):
        """Test client initialization logs different authentication methods correctly."""
        mock_client_instance = Mock()
        mock_ad_manager_client.return_value = mock_client_instance

        with patch("src.adapters.gam.client.GAMAuthManager") as mock_auth_manager:
            mock_auth_instance = Mock()
            mock_credentials = Mock()
            mock_auth_instance.get_credentials.return_value = mock_credentials
            mock_auth_manager.return_value = mock_auth_instance

            # Test OAuth method
            mock_auth_instance.get_auth_method.return_value = "oauth"
            client_manager = GAMClientManager({"refresh_token": "test"}, "12345678")
            client_manager.get_client()

            # Test service account method
            mock_auth_instance.get_auth_method.return_value = "service_account"
            client_manager = GAMClientManager({"key_file": "test.json"}, "12345678")
            client_manager.get_client()

            # Both should succeed
            assert mock_ad_manager_client.call_count == 2
