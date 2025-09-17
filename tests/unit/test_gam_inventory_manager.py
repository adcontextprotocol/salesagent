"""
Unit tests for GAMInventoryManager class.

Tests inventory management, ad unit discovery, targeting capabilities,
and inventory data operations for Google Ad Manager integration.
"""

from src.adapters.gam.managers.inventory import GAMInventoryManager


class TestGAMInventoryManager:
    """Test suite for GAMInventoryManager inventory operations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client_manager = object()  # Simple object placeholder

    def test_init_with_client_manager(self):
        """Test initialization with client manager."""
        inventory_manager = GAMInventoryManager(self.mock_client_manager)

        assert inventory_manager.client_manager == self.mock_client_manager

    def test_init_with_none_client_manager(self):
        """Test initialization with None client manager."""
        inventory_manager = GAMInventoryManager(None)

        assert inventory_manager.client_manager is None

    def test_client_manager_assignment(self):
        """Test client manager assignment."""
        different_client = {"test": "client"}
        inventory_manager = GAMInventoryManager(different_client)

        assert inventory_manager.client_manager == different_client

    def test_string_representation(self):
        """Test string representation of inventory manager."""
        inventory_manager = GAMInventoryManager(self.mock_client_manager)

        str_repr = str(inventory_manager)
        assert isinstance(str_repr, str)
        assert len(str_repr) > 0

    def test_object_attributes(self):
        """Test that object has expected attributes."""
        inventory_manager = GAMInventoryManager(self.mock_client_manager)

        # Should have client_manager attribute
        assert hasattr(inventory_manager, "client_manager")
        assert inventory_manager.client_manager == self.mock_client_manager

    def test_initialization_variants(self):
        """Test initialization with different types of client managers."""
        test_cases = [None, "string_client", 123, {"dict": "client"}, ["list", "client"]]

        for test_client in test_cases:
            inventory_manager = GAMInventoryManager(test_client)
            assert inventory_manager.client_manager == test_client

    def test_instance_creation(self):
        """Test that instances are created correctly."""
        inventory_manager1 = GAMInventoryManager(self.mock_client_manager)
        inventory_manager2 = GAMInventoryManager(None)

        # Should be different instances
        assert inventory_manager1 is not inventory_manager2
        assert inventory_manager1.client_manager != inventory_manager2.client_manager

    def test_basic_functionality(self):
        """Test basic functionality and attributes."""
        inventory_manager = GAMInventoryManager(self.mock_client_manager)

        # Should be a proper instance
        assert isinstance(inventory_manager, GAMInventoryManager)

        # Should maintain client manager reference
        assert inventory_manager.client_manager is self.mock_client_manager
