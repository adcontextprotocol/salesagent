"""Unit tests for GAM AXE segment targeting translation.

Tests that axe_include_segment and axe_exclude_segment fields from AdCP 3.0.3
are correctly translated to GAM custom targeting key-value pairs using
three separate custom targeting keys per AdCP spec.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.adapters.gam.managers.targeting import GAMTargetingManager
from src.core.schemas import Targeting


@pytest.fixture
def mock_adapter_config_three_keys():
    """Fixture for mocked adapter config with all three AXE keys configured."""
    mock_config = MagicMock()
    mock_config.gam_axe_include_key = "audience_include"
    mock_config.gam_axe_exclude_key = "audience_exclude"
    mock_config.gam_axe_macro_key = "audience_macro"
    return mock_config


@pytest.fixture
def mock_adapter_config_no_keys():
    """Fixture for mocked adapter config with no AXE keys configured."""
    mock_config = MagicMock()
    mock_config.gam_axe_include_key = None
    mock_config.gam_axe_exclude_key = None
    mock_config.gam_axe_macro_key = None
    return mock_config


def test_axe_include_segment_translates_to_custom_targeting(mock_adapter_config_three_keys):
    """Test that axe_include_segment translates to GAM custom targeting using configured key."""
    with patch("src.core.database.database_session.get_db_session") as mock_session:
        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        mock_db.scalars.return_value.first.return_value = mock_adapter_config_three_keys

        manager = GAMTargetingManager("tenant_123")

        targeting_overlay = Targeting(
            geo_country_any_of=["US"],
            axe_include_segment="x8dj3k",
        )

        result = manager.build_targeting(targeting_overlay)

        # Verify custom targeting was set with configured "audience_include" key
        assert "customTargeting" in result
        assert "audience_include" in result["customTargeting"]
        assert result["customTargeting"]["audience_include"] == "x8dj3k"


def test_axe_exclude_segment_translates_to_negative_custom_targeting(mock_adapter_config_three_keys):
    """Test that axe_exclude_segment translates to negative GAM custom targeting using configured key."""
    with patch("src.core.database.database_session.get_db_session") as mock_session:
        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        mock_db.scalars.return_value.first.return_value = mock_adapter_config_three_keys

        manager = GAMTargetingManager("tenant_123")

        targeting_overlay = Targeting(
            geo_country_any_of=["US"],
            axe_exclude_segment="y9kl4m",
        )

        result = manager.build_targeting(targeting_overlay)

        # Verify negative custom targeting was set (NOT_ prefix with configured key)
        assert "customTargeting" in result
        assert "NOT_audience_exclude" in result["customTargeting"]
        assert result["customTargeting"]["NOT_audience_exclude"] == "y9kl4m"


def test_axe_segments_both_include_and_exclude(mock_adapter_config_three_keys):
    """Test that both axe_include_segment and axe_exclude_segment can be set with separate keys."""
    with patch("src.core.database.database_session.get_db_session") as mock_session:
        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        mock_db.scalars.return_value.first.return_value = mock_adapter_config_three_keys

        manager = GAMTargetingManager("tenant_123")

        targeting_overlay = Targeting(
            geo_country_any_of=["US"],
            axe_include_segment="x8dj3k",
            axe_exclude_segment="y9kl4m",
        )

        result = manager.build_targeting(targeting_overlay)

        # Verify both positive and negative custom targeting were set with separate keys
        assert "customTargeting" in result
        assert "audience_include" in result["customTargeting"]
        assert result["customTargeting"]["audience_include"] == "x8dj3k"
        assert "NOT_audience_exclude" in result["customTargeting"]
        assert result["customTargeting"]["NOT_audience_exclude"] == "y9kl4m"


def test_axe_segments_combine_with_other_custom_targeting(mock_adapter_config_three_keys):
    """Test that AXE segments combine with other custom targeting."""
    with patch("src.core.database.database_session.get_db_session") as mock_session:
        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        mock_db.scalars.return_value.first.return_value = mock_adapter_config_three_keys

        manager = GAMTargetingManager("tenant_123")

        targeting_overlay = Targeting(
            geo_country_any_of=["US"],
            axe_include_segment="x8dj3k",
            custom={"gam": {"key_values": {"custom_key1": "value1", "custom_key2": "value2"}}},
        )

        result = manager.build_targeting(targeting_overlay)

        # Verify all custom targeting is present
        assert "customTargeting" in result
        assert "audience_include" in result["customTargeting"]
        assert result["customTargeting"]["audience_include"] == "x8dj3k"
        assert "custom_key1" in result["customTargeting"]
        assert result["customTargeting"]["custom_key1"] == "value1"
        assert "custom_key2" in result["customTargeting"]
        assert result["customTargeting"]["custom_key2"] == "value2"


def test_axe_segments_optional(mock_adapter_config_three_keys):
    """Test that AXE segments are optional and don't affect other targeting."""
    with patch("src.core.database.database_session.get_db_session") as mock_session:
        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        mock_db.scalars.return_value.first.return_value = mock_adapter_config_three_keys

        manager = GAMTargetingManager("tenant_123")

        targeting_overlay = Targeting(
            geo_country_any_of=["US"],
            # No axe_include_segment or axe_exclude_segment
        )

        result = manager.build_targeting(targeting_overlay)

        # Verify geo targeting is present but no custom targeting for AXE
        assert "geoTargeting" in result


def test_axe_include_segment_fails_if_key_not_configured(mock_adapter_config_no_keys):
    """Test that axe_include_segment fails with clear error if gam_axe_include_key not configured."""
    with patch("src.core.database.database_session.get_db_session") as mock_session:
        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        mock_db.scalars.return_value.first.return_value = mock_adapter_config_no_keys

        manager = GAMTargetingManager("tenant_123")

        targeting_overlay = Targeting(
            geo_country_any_of=["US"],
            axe_include_segment="x8dj3k",
        )

        with pytest.raises(ValueError) as exc_info:
            manager.build_targeting(targeting_overlay)

        assert "gam_axe_include_key not configured" in str(exc_info.value)


def test_axe_exclude_segment_fails_if_key_not_configured(mock_adapter_config_no_keys):
    """Test that axe_exclude_segment fails with clear error if gam_axe_exclude_key not configured."""
    with patch("src.core.database.database_session.get_db_session") as mock_session:
        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        mock_db.scalars.return_value.first.return_value = mock_adapter_config_no_keys

        manager = GAMTargetingManager("tenant_123")

        targeting_overlay = Targeting(
            geo_country_any_of=["US"],
            axe_exclude_segment="y9kl4m",
        )

        with pytest.raises(ValueError) as exc_info:
            manager.build_targeting(targeting_overlay)

        assert "gam_axe_exclude_key not configured" in str(exc_info.value)
