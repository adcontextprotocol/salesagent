"""
Unit tests for GAMTargetingManager class.

Tests targeting validation, translation from AdCP targeting to GAM targeting,
geo mapping operations, and device/content targeting restrictions.
"""

import json
from unittest.mock import Mock, mock_open, patch

import pytest

from src.adapters.gam.managers.targeting import GAMTargetingManager


class TestGAMTargetingManager:
    """Test suite for GAMTargetingManager targeting operations."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create manager instance
        self.targeting_manager = GAMTargetingManager()

    def test_init_loads_geo_mappings(self):
        """Test initialization loads geo mappings from file."""
        mock_geo_data = {
            "countries": {"US": "2840", "CA": "2124"},
            "regions": {"US": {"CA": "21167", "NY": "21183"}, "CA": {"ON": "20123", "BC": "20456"}},
            "metros": {"US": {"501": "New York", "803": "Los Angeles"}},
        }

        with (
            patch("builtins.open", mock_open(read_data=json.dumps(mock_geo_data))),
            patch("os.path.join") as mock_join,
            patch("os.path.dirname") as mock_dirname,
        ):

            mock_dirname.return_value = "/adapters/gam"
            mock_join.return_value = "/adapters/gam_geo_mappings.json"

            targeting_manager = GAMTargetingManager()

            assert targeting_manager.geo_country_map == {"US": "2840", "CA": "2124"}
            assert targeting_manager.geo_region_map == mock_geo_data["regions"]
            assert targeting_manager.geo_metro_map == {"501": "New York", "803": "Los Angeles"}

    def test_init_missing_geo_file_graceful_handling(self):
        """Test initialization handles missing geo mappings file gracefully."""
        with patch("builtins.open", side_effect=FileNotFoundError("File not found")):
            targeting_manager = GAMTargetingManager()

            assert targeting_manager.geo_country_map == {}
            assert targeting_manager.geo_region_map == {}
            assert targeting_manager.geo_metro_map == {}

    def test_init_malformed_geo_file_graceful_handling(self):
        """Test initialization handles malformed geo mappings file gracefully."""
        with (
            patch("builtins.open", mock_open(read_data="invalid json")),
            patch("json.load", side_effect=json.JSONDecodeError("Invalid JSON", "", 0)),
        ):

            targeting_manager = GAMTargetingManager()

            assert targeting_manager.geo_country_map == {}
            assert targeting_manager.geo_region_map == {}
            assert targeting_manager.geo_metro_map == {}

    def test_device_type_map_constants(self):
        """Test that device type mapping constants are defined correctly."""
        expected_devices = {"mobile": 30000, "desktop": 30001, "tablet": 30002, "ctv": 30003, "dooh": 30004}

        assert GAMTargetingManager.DEVICE_TYPE_MAP == expected_devices

    def test_supported_media_types_constants(self):
        """Test that supported media types are defined correctly."""
        expected_media_types = {"video", "display", "native"}
        assert GAMTargetingManager.SUPPORTED_MEDIA_TYPES == expected_media_types

    def test_lookup_region_id_found(self):
        """Test region ID lookup when region is found."""
        self.targeting_manager.geo_region_map = {
            "US": {"CA": "21167", "NY": "21183"},
            "CA": {"ON": "20123", "BC": "20456"},
        }

        # Should find CA in US
        region_id = self.targeting_manager._lookup_region_id("CA")
        assert region_id == "21167"

        # Should find ON in CA
        region_id = self.targeting_manager._lookup_region_id("ON")
        assert region_id == "20123"

    def test_lookup_region_id_not_found(self):
        """Test region ID lookup when region is not found."""
        self.targeting_manager.geo_region_map = {"US": {"CA": "21167", "NY": "21183"}}

        region_id = self.targeting_manager._lookup_region_id("ZZ")
        assert region_id is None

    def test_validate_targeting_no_targeting(self):
        """Test targeting validation with no targeting overlay."""
        unsupported = self.targeting_manager.validate_targeting(None)
        assert unsupported == []

    def test_validate_targeting_valid_device_types(self):
        """Test targeting validation with valid device types."""
        mock_targeting = Mock()
        mock_targeting.device_type_any_of = ["mobile", "desktop"]
        mock_targeting.media_type_any_of = None

        unsupported = self.targeting_manager.validate_targeting(mock_targeting)
        assert unsupported == []

    def test_validate_targeting_invalid_device_types(self):
        """Test targeting validation with invalid device types."""
        mock_targeting = Mock()
        mock_targeting.device_type_any_of = ["mobile", "invalid_device"]
        mock_targeting.media_type_any_of = None

        unsupported = self.targeting_manager.validate_targeting(mock_targeting)
        assert len(unsupported) == 1
        assert "Device type 'invalid_device' not supported" in unsupported[0]

    def test_validate_targeting_valid_media_types(self):
        """Test targeting validation with valid media types."""
        mock_targeting = Mock()
        mock_targeting.device_type_any_of = None
        mock_targeting.media_type_any_of = ["video", "display"]

        unsupported = self.targeting_manager.validate_targeting(mock_targeting)
        assert unsupported == []

    def test_validate_targeting_invalid_media_types(self):
        """Test targeting validation with invalid media types."""
        mock_targeting = Mock()
        mock_targeting.device_type_any_of = None
        mock_targeting.media_type_any_of = ["display", "invalid_media"]

        unsupported = self.targeting_manager.validate_targeting(mock_targeting)
        assert len(unsupported) == 1
        assert "Media type 'invalid_media' not supported" in unsupported[0]

    def test_validate_targeting_audio_media_type_unsupported(self):
        """Test that audio media type is specifically flagged as unsupported."""
        mock_targeting = Mock()
        mock_targeting.device_type_any_of = None
        mock_targeting.media_type_any_of = ["audio", "display"]

        unsupported = self.targeting_manager.validate_targeting(mock_targeting)
        assert len(unsupported) == 1
        assert "Audio media type not supported by Google Ad Manager" in unsupported[0]

    def test_validate_targeting_city_targeting_unsupported(self):
        """Test that city targeting is flagged as unsupported."""
        mock_targeting = Mock()
        mock_targeting.device_type_any_of = None
        mock_targeting.media_type_any_of = None
        mock_targeting.geo_city_any_of = ["New York"]
        mock_targeting.geo_city_none_of = ["Los Angeles"]

        unsupported = self.targeting_manager.validate_targeting(mock_targeting)
        assert len(unsupported) == 1
        assert "City targeting requires GAM geo service integration" in unsupported[0]

    def test_validate_targeting_postal_targeting_unsupported(self):
        """Test that postal code targeting is flagged as unsupported."""
        mock_targeting = Mock()
        mock_targeting.device_type_any_of = None
        mock_targeting.media_type_any_of = None
        mock_targeting.geo_zip_any_of = ["10001"]
        mock_targeting.geo_zip_none_of = ["90210"]

        unsupported = self.targeting_manager.validate_targeting(mock_targeting)
        assert len(unsupported) == 1
        assert "Postal code targeting requires GAM geo service integration" in unsupported[0]

    def test_build_targeting_no_targeting(self):
        """Test targeting building with no targeting overlay."""
        gam_targeting = self.targeting_manager.build_targeting(None)
        assert gam_targeting == {}

    def test_build_targeting_geo_country_targeting(self):
        """Test targeting building with country geo targeting."""
        self.targeting_manager.geo_country_map = {"US": "2840", "CA": "2124"}

        mock_targeting = Mock()
        mock_targeting.geo_country_any_of = ["US", "CA"]
        mock_targeting.geo_country_none_of = None
        mock_targeting.geo_region_any_of = None
        mock_targeting.geo_metro_any_of = None
        mock_targeting.geo_city_any_of = None
        mock_targeting.geo_zip_any_of = None
        mock_targeting.geo_region_none_of = None
        mock_targeting.geo_metro_none_of = None
        mock_targeting.geo_city_none_of = None
        mock_targeting.geo_zip_none_of = None
        mock_targeting.device_type_any_of = None
        mock_targeting.os_any_of = None
        mock_targeting.browser_any_of = None
        mock_targeting.content_cat_any_of = None
        mock_targeting.keywords_any_of = None
        mock_targeting.custom = None
        mock_targeting.key_value_pairs = None

        gam_targeting = self.targeting_manager.build_targeting(mock_targeting)

        assert "geoTargeting" in gam_targeting
        geo_targeting = gam_targeting["geoTargeting"]
        assert "targetedLocations" in geo_targeting
        assert len(geo_targeting["targetedLocations"]) == 2

        targeted_ids = [loc["id"] for loc in geo_targeting["targetedLocations"]]
        assert "2840" in targeted_ids  # US
        assert "2124" in targeted_ids  # CA

    def test_build_targeting_geo_country_unknown_mapping(self):
        """Test targeting building with unknown country codes."""
        self.targeting_manager.geo_country_map = {"US": "2840"}

        mock_targeting = Mock()
        mock_targeting.geo_country_any_of = ["US", "ZZ"]  # ZZ is unknown
        mock_targeting.geo_country_none_of = None
        mock_targeting.geo_region_any_of = None
        mock_targeting.geo_metro_any_of = None
        mock_targeting.geo_city_any_of = None
        mock_targeting.geo_zip_any_of = None
        mock_targeting.geo_region_none_of = None
        mock_targeting.geo_metro_none_of = None
        mock_targeting.geo_city_none_of = None
        mock_targeting.geo_zip_none_of = None
        mock_targeting.device_type_any_of = None
        mock_targeting.os_any_of = None
        mock_targeting.browser_any_of = None
        mock_targeting.content_cat_any_of = None
        mock_targeting.keywords_any_of = None
        mock_targeting.custom = None
        mock_targeting.key_value_pairs = None

        with patch("src.adapters.gam.managers.targeting.logger") as mock_logger:
            gam_targeting = self.targeting_manager.build_targeting(mock_targeting)

            # Should log warning for unknown country
            mock_logger.warning.assert_called_with("Country code 'ZZ' not in GAM mapping")

            # Should only include known country
            geo_targeting = gam_targeting["geoTargeting"]
            assert len(geo_targeting["targetedLocations"]) == 1
            assert geo_targeting["targetedLocations"][0]["id"] == "2840"

    def test_build_targeting_geo_region_targeting(self):
        """Test targeting building with region geo targeting."""
        self.targeting_manager.geo_region_map = {"US": {"CA": "21167", "NY": "21183"}}

        mock_targeting = Mock()
        mock_targeting.geo_country_any_of = None
        mock_targeting.geo_country_none_of = None
        mock_targeting.geo_region_any_of = ["CA", "NY"]
        mock_targeting.geo_metro_any_of = None
        mock_targeting.geo_city_any_of = None
        mock_targeting.geo_zip_any_of = None
        mock_targeting.geo_region_none_of = None
        mock_targeting.geo_metro_none_of = None
        mock_targeting.geo_city_none_of = None
        mock_targeting.geo_zip_none_of = None
        mock_targeting.device_type_any_of = None
        mock_targeting.os_any_of = None
        mock_targeting.browser_any_of = None
        mock_targeting.content_cat_any_of = None
        mock_targeting.keywords_any_of = None
        mock_targeting.custom = None
        mock_targeting.key_value_pairs = None

        gam_targeting = self.targeting_manager.build_targeting(mock_targeting)

        assert "geoTargeting" in gam_targeting
        geo_targeting = gam_targeting["geoTargeting"]
        assert "targetedLocations" in geo_targeting
        assert len(geo_targeting["targetedLocations"]) == 2

        targeted_ids = [loc["id"] for loc in geo_targeting["targetedLocations"]]
        assert "21167" in targeted_ids  # CA
        assert "21183" in targeted_ids  # NY

    def test_build_targeting_geo_metro_targeting(self):
        """Test targeting building with metro geo targeting."""
        self.targeting_manager.geo_metro_map = {"501": "2501", "803": "2803"}

        mock_targeting = Mock()
        mock_targeting.geo_country_any_of = None
        mock_targeting.geo_country_none_of = None
        mock_targeting.geo_region_any_of = None
        mock_targeting.geo_metro_any_of = ["501", "803"]
        mock_targeting.geo_city_any_of = None
        mock_targeting.geo_zip_any_of = None
        mock_targeting.geo_region_none_of = None
        mock_targeting.geo_metro_none_of = None
        mock_targeting.geo_city_none_of = None
        mock_targeting.geo_zip_none_of = None
        mock_targeting.device_type_any_of = None
        mock_targeting.os_any_of = None
        mock_targeting.browser_any_of = None
        mock_targeting.content_cat_any_of = None
        mock_targeting.keywords_any_of = None
        mock_targeting.custom = None
        mock_targeting.key_value_pairs = None

        gam_targeting = self.targeting_manager.build_targeting(mock_targeting)

        assert "geoTargeting" in gam_targeting
        geo_targeting = gam_targeting["geoTargeting"]
        assert "targetedLocations" in geo_targeting
        assert len(geo_targeting["targetedLocations"]) == 2

    def test_build_targeting_geo_excluded_locations(self):
        """Test targeting building with excluded geo locations."""
        self.targeting_manager.geo_country_map = {"US": "2840", "CA": "2124"}

        mock_targeting = Mock()
        mock_targeting.geo_country_any_of = None
        mock_targeting.geo_country_none_of = ["CA"]
        mock_targeting.geo_region_any_of = None
        mock_targeting.geo_metro_any_of = None
        mock_targeting.geo_city_any_of = None
        mock_targeting.geo_zip_any_of = None
        mock_targeting.geo_region_none_of = None
        mock_targeting.geo_metro_none_of = None
        mock_targeting.geo_city_none_of = None
        mock_targeting.geo_zip_none_of = None
        mock_targeting.device_type_any_of = None
        mock_targeting.os_any_of = None
        mock_targeting.browser_any_of = None
        mock_targeting.content_cat_any_of = None
        mock_targeting.keywords_any_of = None
        mock_targeting.custom = None
        mock_targeting.key_value_pairs = None

        gam_targeting = self.targeting_manager.build_targeting(mock_targeting)

        assert "geoTargeting" in gam_targeting
        geo_targeting = gam_targeting["geoTargeting"]
        assert "excludedLocations" in geo_targeting
        assert len(geo_targeting["excludedLocations"]) == 1
        assert geo_targeting["excludedLocations"][0]["id"] == "2124"

    def test_build_targeting_device_type_fails_loudly(self):
        """Test that device type targeting fails loudly (no quiet failures)."""
        mock_targeting = Mock()
        mock_targeting.geo_country_any_of = None
        mock_targeting.geo_country_none_of = None
        mock_targeting.geo_region_any_of = None
        mock_targeting.geo_metro_any_of = None
        mock_targeting.geo_city_any_of = None
        mock_targeting.geo_zip_any_of = None
        mock_targeting.geo_region_none_of = None
        mock_targeting.geo_metro_none_of = None
        mock_targeting.geo_city_none_of = None
        mock_targeting.geo_zip_none_of = None
        mock_targeting.device_type_any_of = ["mobile", "desktop"]
        mock_targeting.os_any_of = None
        mock_targeting.browser_any_of = None
        mock_targeting.content_cat_any_of = None
        mock_targeting.keywords_any_of = None
        mock_targeting.custom = None
        mock_targeting.key_value_pairs = None

        with pytest.raises(ValueError, match="Device targeting requested but not supported"):
            self.targeting_manager.build_targeting(mock_targeting)

    def test_build_targeting_os_type_fails_loudly(self):
        """Test that OS targeting fails loudly (no quiet failures)."""
        mock_targeting = Mock()
        mock_targeting.geo_country_any_of = None
        mock_targeting.geo_country_none_of = None
        mock_targeting.geo_region_any_of = None
        mock_targeting.geo_metro_any_of = None
        mock_targeting.geo_city_any_of = None
        mock_targeting.geo_zip_any_of = None
        mock_targeting.geo_region_none_of = None
        mock_targeting.geo_metro_none_of = None
        mock_targeting.geo_city_none_of = None
        mock_targeting.geo_zip_none_of = None
        mock_targeting.device_type_any_of = None
        mock_targeting.os_any_of = ["iOS", "Android"]
        mock_targeting.browser_any_of = None
        mock_targeting.content_cat_any_of = None
        mock_targeting.keywords_any_of = None
        mock_targeting.custom = None
        mock_targeting.key_value_pairs = None

        with pytest.raises(ValueError, match="OS targeting requested but not supported"):
            self.targeting_manager.build_targeting(mock_targeting)

    def test_build_targeting_browser_type_fails_loudly(self):
        """Test that browser targeting fails loudly (no quiet failures)."""
        mock_targeting = Mock()
        mock_targeting.geo_country_any_of = None
        mock_targeting.geo_country_none_of = None
        mock_targeting.geo_region_any_of = None
        mock_targeting.geo_metro_any_of = None
        mock_targeting.geo_city_any_of = None
        mock_targeting.geo_zip_any_of = None
        mock_targeting.geo_region_none_of = None
        mock_targeting.geo_metro_none_of = None
        mock_targeting.geo_city_none_of = None
        mock_targeting.geo_zip_none_of = None
        mock_targeting.device_type_any_of = None
        mock_targeting.os_any_of = None
        mock_targeting.browser_any_of = ["Chrome", "Firefox"]
        mock_targeting.content_cat_any_of = None
        mock_targeting.keywords_any_of = None
        mock_targeting.custom = None
        mock_targeting.key_value_pairs = None

        with pytest.raises(ValueError, match="Browser targeting requested but not supported"):
            self.targeting_manager.build_targeting(mock_targeting)

    def test_build_targeting_content_category_fails_loudly(self):
        """Test that content category targeting fails loudly (no quiet failures)."""
        mock_targeting = Mock()
        mock_targeting.geo_country_any_of = None
        mock_targeting.geo_country_none_of = None
        mock_targeting.geo_region_any_of = None
        mock_targeting.geo_metro_any_of = None
        mock_targeting.geo_city_any_of = None
        mock_targeting.geo_zip_any_of = None
        mock_targeting.geo_region_none_of = None
        mock_targeting.geo_metro_none_of = None
        mock_targeting.geo_city_none_of = None
        mock_targeting.geo_zip_none_of = None
        mock_targeting.device_type_any_of = None
        mock_targeting.os_any_of = None
        mock_targeting.browser_any_of = None
        mock_targeting.content_cat_any_of = ["sports", "news"]
        mock_targeting.keywords_any_of = None
        mock_targeting.custom = None
        mock_targeting.key_value_pairs = None

        with pytest.raises(ValueError, match="Content category targeting requested but not supported"):
            self.targeting_manager.build_targeting(mock_targeting)

    def test_build_targeting_keywords_fails_loudly(self):
        """Test that keyword targeting fails loudly (no quiet failures)."""
        mock_targeting = Mock()
        mock_targeting.geo_country_any_of = None
        mock_targeting.geo_country_none_of = None
        mock_targeting.geo_region_any_of = None
        mock_targeting.geo_metro_any_of = None
        mock_targeting.geo_city_any_of = None
        mock_targeting.geo_zip_any_of = None
        mock_targeting.geo_region_none_of = None
        mock_targeting.geo_metro_none_of = None
        mock_targeting.geo_city_none_of = None
        mock_targeting.geo_zip_none_of = None
        mock_targeting.device_type_any_of = None
        mock_targeting.os_any_of = None
        mock_targeting.browser_any_of = None
        mock_targeting.content_cat_any_of = None
        mock_targeting.keywords_any_of = ["sports", "news"]
        mock_targeting.custom = None
        mock_targeting.key_value_pairs = None

        with pytest.raises(ValueError, match="Keyword targeting requested but not supported"):
            self.targeting_manager.build_targeting(mock_targeting)

    def test_build_targeting_custom_gam_targeting(self):
        """Test targeting building with custom GAM targeting."""
        mock_targeting = Mock()
        mock_targeting.geo_country_any_of = None
        mock_targeting.geo_country_none_of = None
        mock_targeting.geo_region_any_of = None
        mock_targeting.geo_metro_any_of = None
        mock_targeting.geo_city_any_of = None
        mock_targeting.geo_zip_any_of = None
        mock_targeting.geo_region_none_of = None
        mock_targeting.geo_metro_none_of = None
        mock_targeting.geo_city_none_of = None
        mock_targeting.geo_zip_none_of = None
        mock_targeting.device_type_any_of = None
        mock_targeting.os_any_of = None
        mock_targeting.browser_any_of = None
        mock_targeting.content_cat_any_of = None
        mock_targeting.keywords_any_of = None
        mock_targeting.custom = {"gam": {"key_values": {"custom_key": "custom_value", "another_key": "another_value"}}}
        mock_targeting.key_value_pairs = None

        gam_targeting = self.targeting_manager.build_targeting(mock_targeting)

        assert "customTargeting" in gam_targeting
        custom_targeting = gam_targeting["customTargeting"]
        assert custom_targeting["custom_key"] == "custom_value"
        assert custom_targeting["another_key"] == "another_value"

    def test_build_targeting_aee_signals_key_value_pairs(self):
        """Test targeting building with AEE signals via key-value pairs."""
        mock_targeting = Mock()
        mock_targeting.geo_country_any_of = None
        mock_targeting.geo_country_none_of = None
        mock_targeting.geo_region_any_of = None
        mock_targeting.geo_metro_any_of = None
        mock_targeting.geo_city_any_of = None
        mock_targeting.geo_zip_any_of = None
        mock_targeting.geo_region_none_of = None
        mock_targeting.geo_metro_none_of = None
        mock_targeting.geo_city_none_of = None
        mock_targeting.geo_zip_none_of = None
        mock_targeting.device_type_any_of = None
        mock_targeting.os_any_of = None
        mock_targeting.browser_any_of = None
        mock_targeting.content_cat_any_of = None
        mock_targeting.keywords_any_of = None
        mock_targeting.custom = None
        mock_targeting.key_value_pairs = {"aee_signal_1": "value_1", "aee_signal_2": "value_2"}

        with patch("src.adapters.gam.managers.targeting.logger") as mock_logger:
            gam_targeting = self.targeting_manager.build_targeting(mock_targeting)

            # Should log AEE signal integration
            mock_logger.info.assert_any_call("Adding AEE signals to GAM key-value targeting")
            mock_logger.info.assert_any_call("  aee_signal_1: value_1")
            mock_logger.info.assert_any_call("  aee_signal_2: value_2")

        assert "customTargeting" in gam_targeting
        custom_targeting = gam_targeting["customTargeting"]
        assert custom_targeting["aee_signal_1"] == "value_1"
        assert custom_targeting["aee_signal_2"] == "value_2"

    def test_build_targeting_combined_custom_and_aee(self):
        """Test targeting building with both custom GAM and AEE signals."""
        mock_targeting = Mock()
        mock_targeting.geo_country_any_of = None
        mock_targeting.geo_country_none_of = None
        mock_targeting.geo_region_any_of = None
        mock_targeting.geo_metro_any_of = None
        mock_targeting.geo_city_any_of = None
        mock_targeting.geo_zip_any_of = None
        mock_targeting.geo_region_none_of = None
        mock_targeting.geo_metro_none_of = None
        mock_targeting.geo_city_none_of = None
        mock_targeting.geo_zip_none_of = None
        mock_targeting.device_type_any_of = None
        mock_targeting.os_any_of = None
        mock_targeting.browser_any_of = None
        mock_targeting.content_cat_any_of = None
        mock_targeting.keywords_any_of = None
        mock_targeting.custom = {"gam": {"key_values": {"custom_key": "custom_value"}}}
        mock_targeting.key_value_pairs = {"aee_signal": "aee_value"}

        gam_targeting = self.targeting_manager.build_targeting(mock_targeting)

        assert "customTargeting" in gam_targeting
        custom_targeting = gam_targeting["customTargeting"]
        assert custom_targeting["custom_key"] == "custom_value"
        assert custom_targeting["aee_signal"] == "aee_value"

    def test_add_inventory_targeting_ad_units(self):
        """Test adding inventory targeting with ad units."""
        targeting = {}

        result = self.targeting_manager.add_inventory_targeting(
            targeting, targeted_ad_unit_ids=["ad_unit_1", "ad_unit_2"], include_descendants=True
        )

        assert "inventoryTargeting" in result
        inventory_targeting = result["inventoryTargeting"]
        assert "targetedAdUnits" in inventory_targeting
        assert len(inventory_targeting["targetedAdUnits"]) == 2

        ad_unit_1 = inventory_targeting["targetedAdUnits"][0]
        assert ad_unit_1["adUnitId"] == "ad_unit_1"
        assert ad_unit_1["includeDescendants"] is True

    def test_add_inventory_targeting_placements(self):
        """Test adding inventory targeting with placements."""
        targeting = {}

        result = self.targeting_manager.add_inventory_targeting(
            targeting, targeted_placement_ids=["placement_1", "placement_2"]
        )

        assert "inventoryTargeting" in result
        inventory_targeting = result["inventoryTargeting"]
        assert "targetedPlacements" in inventory_targeting
        assert len(inventory_targeting["targetedPlacements"]) == 2

        placement_1 = inventory_targeting["targetedPlacements"][0]
        assert placement_1["placementId"] == "placement_1"

    def test_add_inventory_targeting_no_descendants(self):
        """Test adding inventory targeting without including descendants."""
        targeting = {}

        result = self.targeting_manager.add_inventory_targeting(
            targeting, targeted_ad_unit_ids=["ad_unit_1"], include_descendants=False
        )

        ad_unit = result["inventoryTargeting"]["targetedAdUnits"][0]
        assert ad_unit["includeDescendants"] is False

    def test_add_inventory_targeting_no_inventory(self):
        """Test adding inventory targeting with no inventory specified."""
        targeting = {"existing": "data"}

        result = self.targeting_manager.add_inventory_targeting(targeting)

        # Should not add inventory targeting
        assert "inventoryTargeting" not in result
        assert result["existing"] == "data"

    def test_add_custom_targeting(self):
        """Test adding custom targeting keys."""
        targeting = {}
        custom_keys = {"sport": "basketball", "team": "lakers"}

        result = self.targeting_manager.add_custom_targeting(targeting, custom_keys)

        assert "customTargeting" in result
        assert result["customTargeting"]["sport"] == "basketball"
        assert result["customTargeting"]["team"] == "lakers"

    def test_add_custom_targeting_existing_custom(self):
        """Test adding custom targeting keys to existing custom targeting."""
        targeting = {"customTargeting": {"existing_key": "existing_value"}}
        custom_keys = {"new_key": "new_value"}

        result = self.targeting_manager.add_custom_targeting(targeting, custom_keys)

        assert result["customTargeting"]["existing_key"] == "existing_value"
        assert result["customTargeting"]["new_key"] == "new_value"

    def test_add_custom_targeting_empty_keys(self):
        """Test adding empty custom targeting keys."""
        targeting = {"existing": "data"}

        result = self.targeting_manager.add_custom_targeting(targeting, {})

        # Should not add custom targeting
        assert "customTargeting" not in result
        assert result["existing"] == "data"

    def test_add_custom_targeting_none_keys(self):
        """Test adding None custom targeting keys."""
        targeting = {"existing": "data"}

        result = self.targeting_manager.add_custom_targeting(targeting, None)

        # Should not add custom targeting
        assert "customTargeting" not in result
        assert result["existing"] == "data"


class TestGAMTargetingManagerEdgeCases:
    """Test edge cases and boundary conditions."""

    def setup_method(self):
        """Set up test fixtures."""
        self.targeting_manager = GAMTargetingManager()

    def test_build_targeting_city_and_postal_warnings(self):
        """Test that city and postal targeting logs warnings."""
        mock_targeting = Mock()
        mock_targeting.geo_country_any_of = None
        mock_targeting.geo_country_none_of = None
        mock_targeting.geo_region_any_of = None
        mock_targeting.geo_metro_any_of = None
        mock_targeting.geo_city_any_of = ["New York"]
        mock_targeting.geo_zip_any_of = ["10001"]
        mock_targeting.geo_region_none_of = None
        mock_targeting.geo_metro_none_of = None
        mock_targeting.geo_city_none_of = ["Los Angeles"]
        mock_targeting.geo_zip_none_of = ["90210"]
        mock_targeting.device_type_any_of = None
        mock_targeting.os_any_of = None
        mock_targeting.browser_any_of = None
        mock_targeting.content_cat_any_of = None
        mock_targeting.keywords_any_of = None
        mock_targeting.custom = None
        mock_targeting.key_value_pairs = None

        with patch("src.adapters.gam.managers.targeting.logger") as mock_logger:
            gam_targeting = self.targeting_manager.build_targeting(mock_targeting)

            # Should log warnings for both inclusion and exclusion
            mock_logger.warning.assert_any_call("City targeting requires GAM geo service lookup (not implemented)")
            mock_logger.warning.assert_any_call(
                "Postal code targeting requires GAM geo service lookup (not implemented)"
            )
            mock_logger.warning.assert_any_call("City exclusion requires GAM geo service lookup (not implemented)")
            mock_logger.warning.assert_any_call(
                "Postal code exclusion requires GAM geo service lookup (not implemented)"
            )

        # Should not create targeting for unsupported features
        assert "geoTargeting" not in gam_targeting

    def test_build_targeting_empty_geo_lists(self):
        """Test targeting building with empty geo targeting lists."""
        mock_targeting = Mock()
        mock_targeting.geo_country_any_of = []
        mock_targeting.geo_country_none_of = []
        mock_targeting.geo_region_any_of = []
        mock_targeting.geo_metro_any_of = []
        mock_targeting.geo_city_any_of = []
        mock_targeting.geo_zip_any_of = []
        mock_targeting.geo_region_none_of = []
        mock_targeting.geo_metro_none_of = []
        mock_targeting.geo_city_none_of = []
        mock_targeting.geo_zip_none_of = []
        mock_targeting.device_type_any_of = []
        mock_targeting.os_any_of = []
        mock_targeting.browser_any_of = []
        mock_targeting.content_cat_any_of = []
        mock_targeting.keywords_any_of = []
        mock_targeting.custom = None
        mock_targeting.key_value_pairs = None

        gam_targeting = self.targeting_manager.build_targeting(mock_targeting)

        # Should not create any targeting sections
        assert gam_targeting == {}

    def test_validate_targeting_empty_lists(self):
        """Test targeting validation with empty lists."""
        mock_targeting = Mock()
        mock_targeting.device_type_any_of = []
        mock_targeting.media_type_any_of = []

        unsupported = self.targeting_manager.validate_targeting(mock_targeting)
        assert unsupported == []

    def test_validate_targeting_none_lists(self):
        """Test targeting validation with None lists."""
        mock_targeting = Mock()
        mock_targeting.device_type_any_of = None
        mock_targeting.media_type_any_of = None

        unsupported = self.targeting_manager.validate_targeting(mock_targeting)
        assert unsupported == []

    def test_geo_mapping_missing_keys(self):
        """Test geo mapping handling with missing keys in mapping file."""
        mock_geo_data = {
            "countries": {"US": "2840"},
            # Missing regions and metros keys
        }

        with patch("builtins.open", mock_open(read_data=json.dumps(mock_geo_data))):
            targeting_manager = GAMTargetingManager()

            assert targeting_manager.geo_country_map == {"US": "2840"}
            assert targeting_manager.geo_region_map == {}
            assert targeting_manager.geo_metro_map == {}

    def test_geo_mapping_malformed_metros(self):
        """Test geo mapping handling with malformed metros structure."""
        mock_geo_data = {
            "countries": {"US": "2840"},
            "regions": {"US": {"CA": "21167"}},
            "metros": {"CA": {"toronto": "123"}},  # Missing US key
        }

        with patch("builtins.open", mock_open(read_data=json.dumps(mock_geo_data))):
            targeting_manager = GAMTargetingManager()

            assert targeting_manager.geo_metro_map == {}  # US key missing

    def test_error_messages_contain_correct_targeting_values(self):
        """Test that error messages contain the actual targeting values requested."""
        mock_targeting = Mock()
        mock_targeting.geo_country_any_of = None
        mock_targeting.geo_country_none_of = None
        mock_targeting.geo_region_any_of = None
        mock_targeting.geo_metro_any_of = None
        mock_targeting.geo_city_any_of = None
        mock_targeting.geo_zip_any_of = None
        mock_targeting.geo_region_none_of = None
        mock_targeting.geo_metro_none_of = None
        mock_targeting.geo_city_none_of = None
        mock_targeting.geo_zip_none_of = None
        mock_targeting.device_type_any_of = ["mobile", "smartwatch"]
        mock_targeting.os_any_of = None
        mock_targeting.browser_any_of = None
        mock_targeting.content_cat_any_of = None
        mock_targeting.keywords_any_of = None
        mock_targeting.custom = None
        mock_targeting.key_value_pairs = None

        with pytest.raises(ValueError) as exc_info:
            self.targeting_manager.build_targeting(mock_targeting)

        error_message = str(exc_info.value)
        assert "mobile" in error_message
        assert "smartwatch" in error_message
        assert "Cannot fulfill buyer contract" in error_message
