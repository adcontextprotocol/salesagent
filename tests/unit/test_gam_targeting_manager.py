"""
Simplified unit tests for GAMTargetingManager class.

Focuses on core targeting functionality with minimal mocking
to comply with pre-commit limits. Complex targeting scenarios moved to
integration test files.
"""

from src.adapters.gam.managers.targeting import GAMTargetingManager
from tests.unit.helpers.gam_mock_factory import GAMClientMockFactory, GAMTestSetup


class TestGAMTargetingManagerCore:
    """Core functionality tests with minimal mocking."""

    def setup_method(self):
        """Set up test fixtures."""
        self.test_context = GAMTestSetup.create_standard_context()
        self.mock_client_manager = GAMClientMockFactory.create_client_manager()

    def test_init_with_valid_parameters(self):
        """Test initialization with valid parameters."""
        targeting_manager = GAMTargetingManager(self.mock_client_manager, dry_run=False)

        assert targeting_manager.client_manager == self.mock_client_manager
        assert targeting_manager.dry_run is False

    def test_init_with_dry_run_enabled(self):
        """Test initialization with dry_run enabled."""
        targeting_manager = GAMTargetingManager(self.mock_client_manager, dry_run=True)

        assert targeting_manager.dry_run is True

    def test_build_geography_targeting_with_countries(self):
        """Test building geography targeting from country list."""
        targeting_manager = GAMTargetingManager(self.mock_client_manager, dry_run=True)

        countries = ["US", "CA", "GB"]

        result = targeting_manager.build_geography_targeting(countries=countries)

        assert "targetedLocations" in result
        assert len(result["targetedLocations"]) == 3
        # Should create location objects for each country
        for location in result["targetedLocations"]:
            assert "id" in location
            assert "type" in location

    def test_build_geography_targeting_with_regions(self):
        """Test building geography targeting from region list."""
        targeting_manager = GAMTargetingManager(self.mock_client_manager, dry_run=True)

        regions = ["California", "New York", "Texas"]

        result = targeting_manager.build_geography_targeting(regions=regions)

        assert "targetedLocations" in result
        assert len(result["targetedLocations"]) == 3

    def test_build_device_targeting_desktop_mobile(self):
        """Test building device targeting for desktop and mobile."""
        targeting_manager = GAMTargetingManager(self.mock_client_manager, dry_run=True)

        devices = ["desktop", "mobile"]

        result = targeting_manager.build_device_targeting(devices)

        assert "targetedDeviceCategories" in result
        assert len(result["targetedDeviceCategories"]) == 2

    def test_build_demographic_targeting_age_groups(self):
        """Test building demographic targeting with age groups."""
        targeting_manager = GAMTargetingManager(self.mock_client_manager, dry_run=True)

        demographics = {"age_groups": ["18-24", "25-34", "35-44"], "genders": ["male", "female"]}

        result = targeting_manager.build_demographic_targeting(demographics)

        assert "targetedAgeRanges" in result
        assert "targetedGenders" in result
        assert len(result["targetedAgeRanges"]) == 3
        assert len(result["targetedGenders"]) == 2

    def test_build_custom_targeting_key_value_pairs(self):
        """Test building custom targeting from key-value pairs."""
        targeting_manager = GAMTargetingManager(self.mock_client_manager, dry_run=True)

        custom_criteria = {"sport": ["football", "basketball"], "team": ["patriots", "lakers"]}

        result = targeting_manager.build_custom_targeting(custom_criteria)

        assert "customTargeting" in result
        # Should create targeting expressions for each key-value pair
        assert len(result["customTargeting"]) >= len(custom_criteria)

    def test_combine_targeting_criteria_merges_correctly(self):
        """Test that multiple targeting criteria are properly combined."""
        targeting_manager = GAMTargetingManager(self.mock_client_manager, dry_run=True)

        geo_targeting = {"targetedLocations": [{"id": "2840", "type": "COUNTRY"}]}
        device_targeting = {"targetedDeviceCategories": [{"id": "30000"}]}

        result = targeting_manager.combine_targeting_criteria([geo_targeting, device_targeting])

        assert "targetedLocations" in result
        assert "targetedDeviceCategories" in result
        assert len(result["targetedLocations"]) == 1
        assert len(result["targetedDeviceCategories"]) == 1

    def test_validate_targeting_criteria_success(self):
        """Test successful validation of targeting criteria."""
        targeting_manager = GAMTargetingManager(self.mock_client_manager, dry_run=True)

        valid_targeting = {
            "targetedLocations": [{"id": "2840", "type": "COUNTRY"}],
            "targetedDeviceCategories": [{"id": "30000"}],
        }

        # Should not raise any exception
        is_valid = targeting_manager.validate_targeting_criteria(valid_targeting)
        assert is_valid is True

    def test_validate_targeting_criteria_invalid_structure(self):
        """Test validation failure with invalid targeting structure."""
        targeting_manager = GAMTargetingManager(self.mock_client_manager, dry_run=True)

        invalid_targeting = {
            "targetedLocations": "invalid_format",  # Should be list
        }

        is_valid = targeting_manager.validate_targeting_criteria(invalid_targeting)
        assert is_valid is False

    def test_translate_adcp_to_gam_targeting_minimal(self):
        """Test translation of minimal AdCP targeting to GAM format."""
        targeting_manager = GAMTargetingManager(self.mock_client_manager, dry_run=True)

        adcp_targeting = {"countries": ["US", "CA"], "device_type_any_of": ["desktop"]}

        result = targeting_manager.translate_adcp_to_gam_targeting(adcp_targeting)

        assert "targetedLocations" in result
        assert "targetedDeviceCategories" in result


class TestGAMTargetingManagerErrorHandling:
    """Error handling and edge case tests."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client_manager = GAMClientMockFactory.create_client_manager()

    def test_empty_targeting_criteria_returns_empty_result(self):
        """Test that empty targeting criteria returns appropriate empty result."""
        targeting_manager = GAMTargetingManager(self.mock_client_manager, dry_run=True)

        result = targeting_manager.combine_targeting_criteria([])

        assert result == {}

    def test_invalid_country_code_handling(self):
        """Test handling of invalid country codes."""
        targeting_manager = GAMTargetingManager(self.mock_client_manager, dry_run=True)

        # Should handle invalid country codes gracefully
        result = targeting_manager.build_geography_targeting(countries=["INVALID"])

        # Should still return targeting structure (may be empty or with defaults)
        assert "targetedLocations" in result

    def test_duplicate_targeting_criteria_deduplication(self):
        """Test that duplicate targeting criteria are properly deduplicated."""
        targeting_manager = GAMTargetingManager(self.mock_client_manager, dry_run=True)

        targeting1 = {"targetedLocations": [{"id": "2840", "type": "COUNTRY"}]}
        targeting2 = {"targetedLocations": [{"id": "2840", "type": "COUNTRY"}]}  # Duplicate

        result = targeting_manager.combine_targeting_criteria([targeting1, targeting2])

        # Should deduplicate to single location
        assert len(result["targetedLocations"]) == 1
