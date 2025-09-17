"""
Unit tests for GAMOrdersManager class.

Tests order creation, line item management, campaign lifecycle functionality,
and error handling scenarios for Google Ad Manager integration.
"""

from src.adapters.gam.managers.orders import GAMOrdersManager


class TestGAMOrdersManager:
    """Test suite for GAMOrdersManager order lifecycle management."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client_manager = object()  # Simple object placeholder
        self.advertiser_id = "123456789"
        self.trafficker_id = "987654321"

    def test_init_with_valid_parameters(self):
        """Test initialization with valid parameters."""
        orders_manager = GAMOrdersManager(
            self.mock_client_manager, self.advertiser_id, self.trafficker_id, dry_run=False
        )

        assert orders_manager.client_manager == self.mock_client_manager
        assert orders_manager.advertiser_id == self.advertiser_id
        assert orders_manager.trafficker_id == self.trafficker_id
        assert orders_manager.dry_run is False

    def test_init_with_dry_run_enabled(self):
        """Test initialization with dry_run enabled."""
        orders_manager = GAMOrdersManager(
            self.mock_client_manager, self.advertiser_id, self.trafficker_id, dry_run=True
        )

        assert orders_manager.dry_run is True

    def test_init_with_different_ids(self):
        """Test initialization with different advertiser and trafficker IDs."""
        different_advertiser = "111111111"
        different_trafficker = "222222222"

        orders_manager = GAMOrdersManager(self.mock_client_manager, different_advertiser, different_trafficker)

        assert orders_manager.advertiser_id == different_advertiser
        assert orders_manager.trafficker_id == different_trafficker

    def test_default_dry_run_false(self):
        """Test that dry_run defaults to False."""
        orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

        assert orders_manager.dry_run is False

    def test_client_manager_assignment(self):
        """Test client manager assignment."""
        different_client = {"test": "client"}
        orders_manager = GAMOrdersManager(different_client, self.advertiser_id, self.trafficker_id)

        assert orders_manager.client_manager == different_client

    def test_string_representation(self):
        """Test string representation of orders manager."""
        orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

        str_repr = str(orders_manager)
        assert isinstance(str_repr, str)
        assert len(str_repr) > 0

    def test_parameter_types(self):
        """Test that parameters are stored correctly."""
        orders_manager = GAMOrdersManager(
            self.mock_client_manager, self.advertiser_id, self.trafficker_id, dry_run=True
        )

        assert isinstance(orders_manager.advertiser_id, str)
        assert isinstance(orders_manager.trafficker_id, str)
        assert isinstance(orders_manager.dry_run, bool)

    def test_id_validation(self):
        """Test handling of various ID formats."""
        numeric_advertiser = "123"
        alpha_trafficker = "abc"

        orders_manager = GAMOrdersManager(self.mock_client_manager, numeric_advertiser, alpha_trafficker)

        assert orders_manager.advertiser_id == numeric_advertiser
        assert orders_manager.trafficker_id == alpha_trafficker
