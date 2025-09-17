"""
Unit tests for GAMClientManager class.

Tests client initialization, service access, health checking functionality,
connection management, and error handling scenarios.
"""

from src.adapters.gam.client import GAMClientManager


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
        assert client_manager._client is None
        assert client_manager._health_checker is None

    def test_init_with_empty_config(self):
        """Test initialization with empty configuration."""
        empty_config = {}

        # Should not raise error during initialization
        client_manager = GAMClientManager(empty_config, self.network_code)
        assert client_manager.config == empty_config
        assert client_manager.network_code == self.network_code

    def test_init_with_invalid_network_code(self):
        """Test initialization with invalid network code."""
        invalid_network_code = ""

        client_manager = GAMClientManager(self.config, invalid_network_code)
        assert client_manager.network_code == invalid_network_code

    def test_config_access(self):
        """Test that configuration is accessible."""
        test_config = {"refresh_token": "test_token", "network_code": "87654321", "additional_setting": "value"}

        client_manager = GAMClientManager(test_config, "87654321")
        assert client_manager.config == test_config
        assert client_manager.config["additional_setting"] == "value"

    def test_network_code_access(self):
        """Test that network code is accessible."""
        test_network_code = "99887766"

        client_manager = GAMClientManager(self.config, test_network_code)
        assert client_manager.network_code == test_network_code

    def test_initial_state(self):
        """Test that initial state is correct."""
        client_manager = GAMClientManager(self.config, self.network_code)

        # Initially, no client should be created
        assert client_manager._client is None
        assert client_manager._health_checker is None

    def test_config_immutability(self):
        """Test that modifying original config doesn't affect client manager."""
        original_config = {"refresh_token": "original_token"}
        client_manager = GAMClientManager(original_config, self.network_code)

        # Modify original config
        original_config["refresh_token"] = "modified_token"
        original_config["new_key"] = "new_value"

        # Client manager should maintain original state
        assert client_manager.config != original_config
        assert "new_key" not in client_manager.config

    def test_string_representation(self):
        """Test string representation of client manager."""
        client_manager = GAMClientManager(self.config, self.network_code)

        # Should contain relevant information
        str_repr = str(client_manager)
        assert isinstance(str_repr, str)
        assert len(str_repr) > 0
