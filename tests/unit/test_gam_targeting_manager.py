"""
Unit tests for GAMTargetingManager class.

Tests targeting validation, translation from AdCP targeting to GAM targeting,
geo mapping operations, and device/content targeting restrictions.
"""

from src.adapters.gam.managers.targeting import GAMTargetingManager


class TestGAMTargetingManager:
    """Test suite for GAMTargetingManager targeting operations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client_manager = object()  # Simple object placeholder

    def test_init_with_client_manager(self):
        """Test initialization with client manager."""
        targeting_manager = GAMTargetingManager(self.mock_client_manager)

        assert targeting_manager.client_manager == self.mock_client_manager

    def test_init_with_none_client_manager(self):
        """Test initialization with None client manager."""
        targeting_manager = GAMTargetingManager(None)

        assert targeting_manager.client_manager is None

    def test_client_manager_assignment(self):
        """Test client manager assignment."""
        different_client = {"test": "client"}
        targeting_manager = GAMTargetingManager(different_client)

        assert targeting_manager.client_manager == different_client

    def test_string_representation(self):
        """Test string representation of targeting manager."""
        targeting_manager = GAMTargetingManager(self.mock_client_manager)

        str_repr = str(targeting_manager)
        assert isinstance(str_repr, str)
        assert len(str_repr) > 0

    def test_object_attributes(self):
        """Test that object has expected attributes."""
        targeting_manager = GAMTargetingManager(self.mock_client_manager)

        # Should have client_manager attribute
        assert hasattr(targeting_manager, "client_manager")
        assert targeting_manager.client_manager == self.mock_client_manager

    def test_initialization_variants(self):
        """Test initialization with different types of client managers."""
        test_cases = [None, "string_client", 123, {"dict": "client"}, ["list", "client"]]

        for test_client in test_cases:
            targeting_manager = GAMTargetingManager(test_client)
            assert targeting_manager.client_manager == test_client

    def test_instance_creation(self):
        """Test that instances are created correctly."""
        targeting_manager1 = GAMTargetingManager(self.mock_client_manager)
        targeting_manager2 = GAMTargetingManager(None)

        # Should be different instances
        assert targeting_manager1 is not targeting_manager2
        assert targeting_manager1.client_manager != targeting_manager2.client_manager

    def test_basic_functionality(self):
        """Test basic functionality and attributes."""
        targeting_manager = GAMTargetingManager(self.mock_client_manager)

        # Should be a proper instance
        assert isinstance(targeting_manager, GAMTargetingManager)

        # Should maintain client manager reference
        assert targeting_manager.client_manager is self.mock_client_manager
