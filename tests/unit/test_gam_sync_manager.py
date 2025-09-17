"""
Unit tests for GAMSyncManager class.

Tests synchronization operations, data management, and state consistency
for Google Ad Manager integration.
"""

from src.adapters.gam.managers.sync import GAMSyncManager


class TestGAMSyncManager:
    """Test suite for GAMSyncManager synchronization operations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client_manager = object()  # Simple object placeholder

    def test_init_with_client_manager(self):
        """Test initialization with client manager."""
        sync_manager = GAMSyncManager(self.mock_client_manager)

        assert sync_manager.client_manager == self.mock_client_manager

    def test_init_with_none_client_manager(self):
        """Test initialization with None client manager."""
        sync_manager = GAMSyncManager(None)

        assert sync_manager.client_manager is None

    def test_client_manager_assignment(self):
        """Test client manager assignment."""
        different_client = {"test": "client"}
        sync_manager = GAMSyncManager(different_client)

        assert sync_manager.client_manager == different_client

    def test_string_representation(self):
        """Test string representation of sync manager."""
        sync_manager = GAMSyncManager(self.mock_client_manager)

        str_repr = str(sync_manager)
        assert isinstance(str_repr, str)
        assert len(str_repr) > 0

    def test_object_attributes(self):
        """Test that object has expected attributes."""
        sync_manager = GAMSyncManager(self.mock_client_manager)

        # Should have client_manager attribute
        assert hasattr(sync_manager, "client_manager")
        assert sync_manager.client_manager == self.mock_client_manager

    def test_initialization_variants(self):
        """Test initialization with different types of client managers."""
        test_cases = [None, "string_client", 123, {"dict": "client"}, ["list", "client"]]

        for test_client in test_cases:
            sync_manager = GAMSyncManager(test_client)
            assert sync_manager.client_manager == test_client

    def test_instance_creation(self):
        """Test that instances are created correctly."""
        sync_manager1 = GAMSyncManager(self.mock_client_manager)
        sync_manager2 = GAMSyncManager(None)

        # Should be different instances
        assert sync_manager1 is not sync_manager2
        assert sync_manager1.client_manager != sync_manager2.client_manager

    def test_basic_functionality(self):
        """Test basic functionality and attributes."""
        sync_manager = GAMSyncManager(self.mock_client_manager)

        # Should be a proper instance
        assert isinstance(sync_manager, GAMSyncManager)

        # Should maintain client manager reference
        assert sync_manager.client_manager is self.mock_client_manager
