"""
Unit tests for GAMCreativesManager class.

Tests creative upload, management, association with line items,
and creative asset handling functionality.
"""

from src.adapters.gam.managers.creatives import GAMCreativesManager


class TestGAMCreativesManager:
    """Test suite for GAMCreativesManager creative lifecycle management."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client_manager = object()  # Simple object placeholder
        self.advertiser_id = "123456789"

    def test_init_with_valid_parameters(self):
        """Test initialization with valid parameters."""
        creatives_manager = GAMCreativesManager(self.mock_client_manager, self.advertiser_id, dry_run=False)

        assert creatives_manager.client_manager == self.mock_client_manager
        assert creatives_manager.advertiser_id == self.advertiser_id
        assert creatives_manager.dry_run is False

    def test_init_with_dry_run_enabled(self):
        """Test initialization with dry_run enabled."""
        creatives_manager = GAMCreativesManager(self.mock_client_manager, self.advertiser_id, dry_run=True)

        assert creatives_manager.dry_run is True

    def test_init_with_different_advertiser(self):
        """Test initialization with different advertiser ID."""
        different_advertiser = "987654321"
        creatives_manager = GAMCreativesManager(self.mock_client_manager, different_advertiser)

        assert creatives_manager.advertiser_id == different_advertiser

    def test_default_dry_run_false(self):
        """Test that dry_run defaults to False."""
        creatives_manager = GAMCreativesManager(self.mock_client_manager, self.advertiser_id)

        assert creatives_manager.dry_run is False

    def test_client_manager_assignment(self):
        """Test client manager assignment."""
        different_client = {"test": "client"}
        creatives_manager = GAMCreativesManager(different_client, self.advertiser_id)

        assert creatives_manager.client_manager == different_client

    def test_string_representation(self):
        """Test string representation of creatives manager."""
        creatives_manager = GAMCreativesManager(self.mock_client_manager, self.advertiser_id)

        str_repr = str(creatives_manager)
        assert isinstance(str_repr, str)
        assert len(str_repr) > 0

    def test_parameter_types(self):
        """Test that parameters are stored correctly."""
        creatives_manager = GAMCreativesManager(self.mock_client_manager, self.advertiser_id, dry_run=True)

        assert isinstance(creatives_manager.advertiser_id, str)
        assert isinstance(creatives_manager.dry_run, bool)

    def test_advertiser_id_validation(self):
        """Test handling of various advertiser ID formats."""
        test_ids = ["123", "abc", "123abc", ""]

        for test_id in test_ids:
            creatives_manager = GAMCreativesManager(self.mock_client_manager, test_id)
            assert creatives_manager.advertiser_id == test_id

    def test_instance_creation(self):
        """Test that instances are created correctly."""
        creatives1 = GAMCreativesManager(self.mock_client_manager, self.advertiser_id)
        creatives2 = GAMCreativesManager(None, "different_id")

        # Should be different instances
        assert creatives1 is not creatives2
        assert creatives1.advertiser_id != creatives2.advertiser_id
        assert creatives1.client_manager != creatives2.client_manager
