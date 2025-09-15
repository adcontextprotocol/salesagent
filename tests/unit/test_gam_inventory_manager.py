"""
Unit tests for GAMInventoryManager class.

Tests inventory discovery, caching, ad unit management, placement operations,
and integration with GAM client for inventory operations.
"""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from src.adapters.gam.managers.inventory import GAMInventoryManager, MockGAMInventoryDiscovery


class TestGAMInventoryManager:
    """Test suite for GAMInventoryManager inventory operations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client_manager = Mock()
        self.tenant_id = "test_tenant_123"

        self.inventory_manager = GAMInventoryManager(self.mock_client_manager, self.tenant_id, dry_run=False)

    def test_init_with_valid_parameters(self):
        """Test initialization with valid parameters."""
        inventory_manager = GAMInventoryManager(self.mock_client_manager, self.tenant_id, dry_run=True)

        assert inventory_manager.client_manager == self.mock_client_manager
        assert inventory_manager.tenant_id == self.tenant_id
        assert inventory_manager.dry_run is True
        assert inventory_manager._discovery is None
        assert inventory_manager._cache_timeout == timedelta(hours=24)

    def test_get_discovery_creates_real_discovery(self):
        """Test _get_discovery creates real GAMInventoryDiscovery instance."""
        mock_client = Mock()
        self.mock_client_manager.get_client.return_value = mock_client

        with patch("src.adapters.gam.managers.inventory.GAMInventoryDiscovery") as mock_discovery_class:
            mock_discovery_instance = Mock()
            mock_discovery_class.return_value = mock_discovery_instance

            discovery = self.inventory_manager._get_discovery()

            mock_discovery_class.assert_called_once_with(mock_client, self.tenant_id)
            assert discovery == mock_discovery_instance
            assert self.inventory_manager._discovery == mock_discovery_instance

    def test_get_discovery_creates_mock_discovery_in_dry_run(self):
        """Test _get_discovery creates MockGAMInventoryDiscovery in dry-run mode."""
        self.inventory_manager.dry_run = True

        discovery = self.inventory_manager._get_discovery()

        assert isinstance(discovery, MockGAMInventoryDiscovery)
        assert discovery.tenant_id == self.tenant_id
        assert self.inventory_manager._discovery == discovery

    def test_get_discovery_returns_cached_instance(self):
        """Test _get_discovery returns cached discovery instance."""
        mock_discovery = Mock()
        self.inventory_manager._discovery = mock_discovery

        discovery = self.inventory_manager._get_discovery()

        assert discovery == mock_discovery
        # Should not create new instance
        self.mock_client_manager.get_client.assert_not_called()

    def test_discover_ad_units_success(self):
        """Test successful ad unit discovery."""
        mock_discovery = Mock()
        mock_ad_units = [Mock(id="ad_unit_1", name="Sports Section"), Mock(id="ad_unit_2", name="News Section")]
        mock_discovery.discover_ad_units.return_value = mock_ad_units
        self.inventory_manager._discovery = mock_discovery

        result = self.inventory_manager.discover_ad_units(parent_id="root", max_depth=5)

        assert result == mock_ad_units
        mock_discovery.discover_ad_units.assert_called_once_with("root", 5)

    def test_discover_ad_units_dry_run(self):
        """Test ad unit discovery in dry-run mode."""
        self.inventory_manager.dry_run = True

        result = self.inventory_manager.discover_ad_units(parent_id="root", max_depth=10)

        assert result == []
        # Should not call client manager
        self.mock_client_manager.get_client.assert_not_called()

    def test_discover_ad_units_default_parameters(self):
        """Test ad unit discovery with default parameters."""
        mock_discovery = Mock()
        mock_discovery.discover_ad_units.return_value = []
        self.inventory_manager._discovery = mock_discovery

        self.inventory_manager.discover_ad_units()

        mock_discovery.discover_ad_units.assert_called_once_with(None, 10)

    def test_discover_placements_success(self):
        """Test successful placement discovery."""
        mock_discovery = Mock()
        mock_placements = [Mock(id="placement_1", name="Homepage Banner"), Mock(id="placement_2", name="Sidebar Ads")]
        mock_discovery.discover_placements.return_value = mock_placements
        self.inventory_manager._discovery = mock_discovery

        result = self.inventory_manager.discover_placements()

        assert result == mock_placements
        mock_discovery.discover_placements.assert_called_once()

    def test_discover_placements_dry_run(self):
        """Test placement discovery in dry-run mode."""
        self.inventory_manager.dry_run = True

        result = self.inventory_manager.discover_placements()

        assert result == []

    def test_discover_custom_targeting_success(self):
        """Test successful custom targeting discovery."""
        mock_discovery = Mock()
        mock_targeting_data = {
            "keys": [{"id": "key_1", "name": "sport"}, {"id": "key_2", "name": "team"}],
            "total_values": 25,
        }
        mock_discovery.discover_custom_targeting.return_value = mock_targeting_data
        self.inventory_manager._discovery = mock_discovery

        result = self.inventory_manager.discover_custom_targeting()

        assert result == mock_targeting_data
        mock_discovery.discover_custom_targeting.assert_called_once()

    def test_discover_custom_targeting_dry_run(self):
        """Test custom targeting discovery in dry-run mode."""
        self.inventory_manager.dry_run = True

        result = self.inventory_manager.discover_custom_targeting()

        assert result == {"keys": [], "total_values": 0}

    def test_discover_audience_segments_success(self):
        """Test successful audience segment discovery."""
        mock_discovery = Mock()
        mock_segments = [Mock(id="segment_1", name="Sports Fans"), Mock(id="segment_2", name="Tech Enthusiasts")]
        mock_discovery.discover_audience_segments.return_value = mock_segments
        self.inventory_manager._discovery = mock_discovery

        result = self.inventory_manager.discover_audience_segments()

        assert result == mock_segments
        mock_discovery.discover_audience_segments.assert_called_once()

    def test_discover_audience_segments_dry_run(self):
        """Test audience segment discovery in dry-run mode."""
        self.inventory_manager.dry_run = True

        result = self.inventory_manager.discover_audience_segments()

        assert result == []

    def test_discover_labels_success(self):
        """Test successful label discovery."""
        mock_discovery = Mock()
        mock_labels = [Mock(id="label_1", name="Premium Content"), Mock(id="label_2", name="Sports Only")]
        mock_discovery.discover_labels.return_value = mock_labels
        self.inventory_manager._discovery = mock_discovery

        result = self.inventory_manager.discover_labels()

        assert result == mock_labels
        mock_discovery.discover_labels.assert_called_once()

    def test_discover_labels_dry_run(self):
        """Test label discovery in dry-run mode."""
        self.inventory_manager.dry_run = True

        result = self.inventory_manager.discover_labels()

        assert result == []

    def test_sync_all_inventory_success(self):
        """Test successful full inventory sync."""
        mock_discovery = Mock()
        mock_sync_result = {
            "tenant_id": self.tenant_id,
            "sync_time": datetime.now().isoformat(),
            "ad_units": {"total": 15, "active": 12},
            "placements": {"total": 8, "active": 6},
            "labels": {"total": 5, "active": 5},
            "custom_targeting": {"total_keys": 10, "total_values": 150},
            "audience_segments": {"total": 25, "active": 20},
        }
        mock_discovery.sync_all.return_value = mock_sync_result
        self.inventory_manager._discovery = mock_discovery

        result = self.inventory_manager.sync_all_inventory()

        assert result == mock_sync_result
        mock_discovery.sync_all.assert_called_once()

    def test_sync_all_inventory_dry_run(self):
        """Test full inventory sync in dry-run mode."""
        self.inventory_manager.dry_run = True

        result = self.inventory_manager.sync_all_inventory()

        assert result["tenant_id"] == self.tenant_id
        assert result["dry_run"] is True
        assert "sync_time" in result
        assert "ad_units" in result
        assert "placements" in result

    def test_build_ad_unit_tree_success(self):
        """Test successful ad unit tree building."""
        mock_discovery = Mock()
        mock_tree = {
            "root_units": [
                {"id": "root_1", "name": "Sports", "children": []},
                {"id": "root_2", "name": "News", "children": []},
            ],
            "total_units": 25,
            "last_sync": datetime.now().isoformat(),
        }
        mock_discovery.build_ad_unit_tree.return_value = mock_tree
        self.inventory_manager._discovery = mock_discovery

        result = self.inventory_manager.build_ad_unit_tree()

        assert result == mock_tree
        mock_discovery.build_ad_unit_tree.assert_called_once()

    def test_build_ad_unit_tree_dry_run(self):
        """Test ad unit tree building in dry-run mode."""
        self.inventory_manager.dry_run = True

        result = self.inventory_manager.build_ad_unit_tree()

        assert result["root_units"] == []
        assert result["total_units"] == 0
        assert result["dry_run"] is True

    def test_get_targetable_ad_units_success(self):
        """Test successful targetable ad units retrieval."""
        mock_discovery = Mock()
        mock_ad_units = [
            Mock(id="ad_unit_1", name="Sports Banner", explicitly_targeted=True),
            Mock(id="ad_unit_2", name="News Sidebar", explicitly_targeted=True),
        ]
        mock_discovery.get_targetable_ad_units.return_value = mock_ad_units
        self.inventory_manager._discovery = mock_discovery

        result = self.inventory_manager.get_targetable_ad_units(
            include_inactive=True, min_sizes=[{"width": 300, "height": 250}]
        )

        assert result == mock_ad_units
        mock_discovery.get_targetable_ad_units.assert_called_once_with(True, [{"width": 300, "height": 250}])

    def test_get_targetable_ad_units_dry_run(self):
        """Test targetable ad units retrieval in dry-run mode."""
        self.inventory_manager.dry_run = True

        result = self.inventory_manager.get_targetable_ad_units()

        assert result == []

    def test_suggest_ad_units_for_product_success(self):
        """Test successful ad unit suggestions for product."""
        mock_discovery = Mock()
        mock_suggestions = [
            {"ad_unit_id": "unit_1", "score": 0.95, "reasons": ["size_match", "keyword_match"]},
            {"ad_unit_id": "unit_2", "score": 0.80, "reasons": ["size_match"]},
        ]
        mock_discovery.suggest_ad_units_for_product.return_value = mock_suggestions
        self.inventory_manager._discovery = mock_discovery

        creative_sizes = [{"width": 728, "height": 90}]
        keywords = ["sports", "basketball"]

        result = self.inventory_manager.suggest_ad_units_for_product(creative_sizes, keywords)

        assert result == mock_suggestions
        mock_discovery.suggest_ad_units_for_product.assert_called_once_with(creative_sizes, keywords)

    def test_suggest_ad_units_for_product_dry_run(self):
        """Test ad unit suggestions in dry-run mode."""
        self.inventory_manager.dry_run = True

        result = self.inventory_manager.suggest_ad_units_for_product([])

        assert result == []

    def test_get_placements_for_ad_units_success(self):
        """Test successful placement retrieval for ad units."""
        mock_discovery = Mock()
        mock_placements = [
            Mock(id="placement_1", name="Sports Placement"),
            Mock(id="placement_2", name="News Placement"),
        ]
        mock_discovery.get_placements_for_ad_units.return_value = mock_placements
        self.inventory_manager._discovery = mock_discovery

        ad_unit_ids = ["unit_1", "unit_2"]
        result = self.inventory_manager.get_placements_for_ad_units(ad_unit_ids)

        assert result == mock_placements
        mock_discovery.get_placements_for_ad_units.assert_called_once_with(ad_unit_ids)

    def test_get_placements_for_ad_units_dry_run(self):
        """Test placement retrieval for ad units in dry-run mode."""
        self.inventory_manager.dry_run = True

        result = self.inventory_manager.get_placements_for_ad_units(["unit_1"])

        assert result == []

    def test_save_to_cache_success(self):
        """Test successful cache saving."""
        mock_discovery = Mock()
        self.inventory_manager._discovery = mock_discovery

        cache_dir = "/tmp/cache"
        self.inventory_manager.save_to_cache(cache_dir)

        mock_discovery.save_to_cache.assert_called_once_with(cache_dir)

    def test_save_to_cache_dry_run(self):
        """Test cache saving in dry-run mode."""
        self.inventory_manager.dry_run = True

        # Should not raise exception
        self.inventory_manager.save_to_cache("/tmp/cache")

    def test_load_from_cache_success(self):
        """Test successful cache loading."""
        mock_discovery = Mock()
        mock_discovery.load_from_cache.return_value = True
        self.inventory_manager._discovery = mock_discovery

        cache_dir = "/tmp/cache"
        result = self.inventory_manager.load_from_cache(cache_dir)

        assert result is True
        mock_discovery.load_from_cache.assert_called_once_with(cache_dir)

    def test_load_from_cache_failure(self):
        """Test cache loading failure."""
        mock_discovery = Mock()
        mock_discovery.load_from_cache.return_value = False
        self.inventory_manager._discovery = mock_discovery

        result = self.inventory_manager.load_from_cache("/tmp/cache")

        assert result is False

    def test_load_from_cache_dry_run(self):
        """Test cache loading in dry-run mode."""
        self.inventory_manager.dry_run = True

        result = self.inventory_manager.load_from_cache("/tmp/cache")

        assert result is False

    def test_get_inventory_summary_success(self):
        """Test successful inventory summary retrieval."""
        mock_discovery = Mock()
        mock_discovery.ad_units = {"unit_1": Mock(), "unit_2": Mock()}
        mock_discovery.placements = {"placement_1": Mock()}
        mock_discovery.labels = {"label_1": Mock(), "label_2": Mock()}
        mock_discovery.custom_targeting_keys = {"key_1": Mock()}
        mock_discovery.audience_segments = {"segment_1": Mock()}
        mock_discovery.last_sync = datetime(2025, 1, 15, 10, 30, 0)
        self.inventory_manager._discovery = mock_discovery

        result = self.inventory_manager.get_inventory_summary()

        assert result["tenant_id"] == self.tenant_id
        assert result["ad_units"] == 2
        assert result["placements"] == 1
        assert result["labels"] == 2
        assert result["custom_targeting_keys"] == 1
        assert result["audience_segments"] == 1
        assert result["last_sync"] == "2025-01-15T10:30:00"

    def test_get_inventory_summary_no_last_sync(self):
        """Test inventory summary with no last sync time."""
        mock_discovery = Mock()
        mock_discovery.ad_units = {}
        mock_discovery.placements = {}
        mock_discovery.labels = {}
        mock_discovery.custom_targeting_keys = {}
        mock_discovery.audience_segments = {}
        mock_discovery.last_sync = None
        self.inventory_manager._discovery = mock_discovery

        result = self.inventory_manager.get_inventory_summary()

        assert result["last_sync"] is None

    def test_get_inventory_summary_dry_run(self):
        """Test inventory summary in dry-run mode."""
        self.inventory_manager.dry_run = True

        result = self.inventory_manager.get_inventory_summary()

        assert result["tenant_id"] == self.tenant_id
        assert result["dry_run"] is True
        assert result["ad_units"] == 0
        assert result["placements"] == 0
        assert result["labels"] == 0
        assert result["custom_targeting_keys"] == 0
        assert result["audience_segments"] == 0
        assert result["last_sync"] is None

    def test_validate_inventory_access_success(self):
        """Test successful inventory access validation."""
        mock_discovery = Mock()
        mock_unit_1 = Mock()
        mock_unit_1.explicitly_targeted = True
        mock_unit_1.status.value = "ACTIVE"

        mock_unit_2 = Mock()
        mock_unit_2.explicitly_targeted = False
        mock_unit_2.status.value = "ACTIVE"

        mock_discovery.ad_units = {"unit_1": mock_unit_1, "unit_2": mock_unit_2}
        self.inventory_manager._discovery = mock_discovery

        result = self.inventory_manager.validate_inventory_access(["unit_1", "unit_2", "unit_3"])

        assert result["unit_1"] is True  # explicitly targeted
        assert result["unit_2"] is True  # active status
        assert result["unit_3"] is False  # not found

    def test_validate_inventory_access_inactive_unit(self):
        """Test inventory access validation with inactive unit."""
        mock_discovery = Mock()
        mock_unit = Mock()
        mock_unit.explicitly_targeted = False
        mock_unit.status.value = "INACTIVE"

        mock_discovery.ad_units = {"unit_1": mock_unit}
        self.inventory_manager._discovery = mock_discovery

        result = self.inventory_manager.validate_inventory_access(["unit_1"])

        assert result["unit_1"] is False

    def test_validate_inventory_access_dry_run(self):
        """Test inventory access validation in dry-run mode."""
        self.inventory_manager.dry_run = True

        result = self.inventory_manager.validate_inventory_access(["unit_1", "unit_2"])

        assert result["unit_1"] is True
        assert result["unit_2"] is True


class TestMockGAMInventoryDiscovery:
    """Test suite for MockGAMInventoryDiscovery class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tenant_id = "test_tenant_123"
        self.mock_discovery = MockGAMInventoryDiscovery(None, self.tenant_id)

    def test_init_with_parameters(self):
        """Test MockGAMInventoryDiscovery initialization."""
        assert self.mock_discovery.client is None
        assert self.mock_discovery.tenant_id == self.tenant_id
        assert self.mock_discovery.ad_units == {}
        assert self.mock_discovery.placements == {}
        assert self.mock_discovery.labels == {}
        assert self.mock_discovery.custom_targeting_keys == {}
        assert self.mock_discovery.custom_targeting_values == {}
        assert self.mock_discovery.audience_segments == {}
        assert self.mock_discovery.last_sync is None

    def test_discover_ad_units_mock(self):
        """Test mock ad unit discovery."""
        result = self.mock_discovery.discover_ad_units(parent_id="root", max_depth=5)
        assert result == []

    def test_discover_placements_mock(self):
        """Test mock placement discovery."""
        result = self.mock_discovery.discover_placements()
        assert result == []

    def test_discover_custom_targeting_mock(self):
        """Test mock custom targeting discovery."""
        result = self.mock_discovery.discover_custom_targeting()
        assert result == {"keys": [], "total_values": 0}

    def test_discover_audience_segments_mock(self):
        """Test mock audience segment discovery."""
        result = self.mock_discovery.discover_audience_segments()
        assert result == []

    def test_discover_labels_mock(self):
        """Test mock label discovery."""
        result = self.mock_discovery.discover_labels()
        assert result == []

    def test_sync_all_mock(self):
        """Test mock full sync operation."""
        result = self.mock_discovery.sync_all()

        assert result["tenant_id"] == self.tenant_id
        assert result["dry_run"] is True
        assert "sync_time" in result
        assert result["ad_units"]["total"] == 0
        assert result["placements"]["total"] == 0
        assert result["labels"]["total"] == 0
        assert result["custom_targeting"]["total_keys"] == 0
        assert result["audience_segments"]["total"] == 0

    def test_build_ad_unit_tree_mock(self):
        """Test mock ad unit tree building."""
        result = self.mock_discovery.build_ad_unit_tree()

        assert result["root_units"] == []
        assert result["total_units"] == 0
        assert result["dry_run"] is True
        assert "last_sync" in result

    def test_get_targetable_ad_units_mock(self):
        """Test mock targetable ad units retrieval."""
        result = self.mock_discovery.get_targetable_ad_units(
            include_inactive=True, min_sizes=[{"width": 300, "height": 250}]
        )
        assert result == []

    def test_suggest_ad_units_for_product_mock(self):
        """Test mock ad unit suggestions."""
        result = self.mock_discovery.suggest_ad_units_for_product(
            creative_sizes=[{"width": 728, "height": 90}], keywords=["sports"]
        )
        assert result == []

    def test_get_placements_for_ad_units_mock(self):
        """Test mock placement retrieval for ad units."""
        result = self.mock_discovery.get_placements_for_ad_units(["unit_1", "unit_2"])
        assert result == []

    def test_save_to_cache_mock(self):
        """Test mock cache saving."""
        # Should not raise exception
        self.mock_discovery.save_to_cache("/tmp/cache")

    def test_load_from_cache_mock(self):
        """Test mock cache loading."""
        result = self.mock_discovery.load_from_cache("/tmp/cache")
        assert result is False


class TestGAMInventoryManagerEdgeCases:
    """Test edge cases and boundary conditions."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client_manager = Mock()
        self.tenant_id = "test_tenant_123"
        self.inventory_manager = GAMInventoryManager(self.mock_client_manager, self.tenant_id, dry_run=False)

    def test_init_with_empty_tenant_id(self):
        """Test initialization with empty tenant ID."""
        inventory_manager = GAMInventoryManager(self.mock_client_manager, "", dry_run=False)

        assert inventory_manager.tenant_id == ""

    def test_init_with_none_tenant_id(self):
        """Test initialization with None tenant ID."""
        inventory_manager = GAMInventoryManager(self.mock_client_manager, None, dry_run=False)

        assert inventory_manager.tenant_id is None

    def test_get_discovery_with_client_error(self):
        """Test _get_discovery when client manager fails."""
        self.mock_client_manager.get_client.side_effect = Exception("Client error")

        with pytest.raises(Exception, match="Client error"):
            self.inventory_manager._get_discovery()

    def test_discover_methods_with_discovery_errors(self):
        """Test discovery methods when underlying discovery raises errors."""
        mock_discovery = Mock()
        mock_discovery.discover_ad_units.side_effect = Exception("Discovery error")
        self.inventory_manager._discovery = mock_discovery

        # Should propagate the error
        with pytest.raises(Exception, match="Discovery error"):
            self.inventory_manager.discover_ad_units()

    def test_sync_all_inventory_with_error(self):
        """Test sync_all_inventory when discovery sync fails."""
        mock_discovery = Mock()
        mock_discovery.sync_all.side_effect = Exception("Sync failed")
        self.inventory_manager._discovery = mock_discovery

        with pytest.raises(Exception, match="Sync failed"):
            self.inventory_manager.sync_all_inventory()

    def test_validate_inventory_access_empty_list(self):
        """Test inventory access validation with empty ad unit list."""
        mock_discovery = Mock()
        mock_discovery.ad_units = {}
        self.inventory_manager._discovery = mock_discovery

        result = self.inventory_manager.validate_inventory_access([])

        assert result == {}

    def test_validate_inventory_access_unit_missing_attributes(self):
        """Test inventory access validation with units missing attributes."""
        mock_discovery = Mock()
        mock_unit = Mock()
        # Remove attributes to test graceful handling
        del mock_unit.explicitly_targeted
        del mock_unit.status

        mock_discovery.ad_units = {"unit_1": mock_unit}
        self.inventory_manager._discovery = mock_discovery

        # Should handle missing attributes gracefully
        with pytest.raises(AttributeError):
            self.inventory_manager.validate_inventory_access(["unit_1"])

    def test_cache_operations_with_none_paths(self):
        """Test cache operations with None cache paths."""
        mock_discovery = Mock()
        self.inventory_manager._discovery = mock_discovery

        # Should handle None paths gracefully
        self.inventory_manager.save_to_cache(None)
        result = self.inventory_manager.load_from_cache(None)

        # Discovery methods should still be called
        mock_discovery.save_to_cache.assert_called_once_with(None)
        mock_discovery.load_from_cache.assert_called_once_with(None)

    def test_suggest_ad_units_with_none_parameters(self):
        """Test ad unit suggestions with None parameters."""
        mock_discovery = Mock()
        mock_discovery.suggest_ad_units_for_product.return_value = []
        self.inventory_manager._discovery = mock_discovery

        result = self.inventory_manager.suggest_ad_units_for_product(None, None)

        assert result == []
        mock_discovery.suggest_ad_units_for_product.assert_called_once_with(None, None)

    def test_get_placements_for_ad_units_empty_list(self):
        """Test placement retrieval with empty ad unit list."""
        mock_discovery = Mock()
        mock_discovery.get_placements_for_ad_units.return_value = []
        self.inventory_manager._discovery = mock_discovery

        result = self.inventory_manager.get_placements_for_ad_units([])

        assert result == []
        mock_discovery.get_placements_for_ad_units.assert_called_once_with([])

    def test_discovery_initialization_only_when_needed(self):
        """Test that discovery is only initialized when actually needed."""
        # Just creating the manager shouldn't initialize discovery
        assert self.inventory_manager._discovery is None

        # Only when calling a method that needs discovery should it be initialized
        with patch.object(self.inventory_manager, "_get_discovery") as mock_get_discovery:
            mock_discovery = Mock()
            mock_get_discovery.return_value = mock_discovery

            self.inventory_manager.discover_ad_units()

            mock_get_discovery.assert_called_once()

    def test_cache_timeout_configuration(self):
        """Test that cache timeout is properly configured."""
        assert self.inventory_manager._cache_timeout == timedelta(hours=24)

        # Test with custom timeout (if constructor were to support it)
        inventory_manager = GAMInventoryManager(self.mock_client_manager, self.tenant_id, dry_run=False)
        assert inventory_manager._cache_timeout == timedelta(hours=24)
