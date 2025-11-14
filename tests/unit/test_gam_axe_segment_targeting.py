"""Unit tests for GAM AXE segment targeting translation.

Tests that axe_include_segment and axe_exclude_segment fields from AdCP 3.0.3
are correctly translated to GAM custom targeting key-value pairs.

Note: Current implementation uses hardcoded "axe_segment" key name.
TODO: Add tests for custom key name configuration once implemented.
"""

from src.adapters.gam.managers.targeting import GAMTargetingManager
from src.core.schemas import Targeting


def test_axe_include_segment_translates_to_custom_targeting():
    """Test that axe_include_segment translates to GAM custom targeting."""
    manager = GAMTargetingManager()

    targeting_overlay = Targeting(
        geo_country_any_of=["US"],
        axe_include_segment="x8dj3k",
    )

    result = manager.build_targeting(targeting_overlay)

    # Verify custom targeting was set with default "axe_segment" key
    assert "customTargeting" in result
    assert "axe_segment" in result["customTargeting"]
    assert result["customTargeting"]["axe_segment"] == "x8dj3k"


def test_axe_exclude_segment_translates_to_negative_custom_targeting():
    """Test that axe_exclude_segment translates to negative GAM custom targeting."""
    manager = GAMTargetingManager()

    targeting_overlay = Targeting(
        geo_country_any_of=["US"],
        axe_exclude_segment="y9kl4m",
    )

    result = manager.build_targeting(targeting_overlay)

    # Verify negative custom targeting was set (NOT_ prefix)
    assert "customTargeting" in result
    assert "NOT_axe_segment" in result["customTargeting"]
    assert result["customTargeting"]["NOT_axe_segment"] == "y9kl4m"


def test_axe_segments_both_include_and_exclude():
    """Test that both axe_include_segment and axe_exclude_segment can be set."""
    manager = GAMTargetingManager()

    targeting_overlay = Targeting(
        geo_country_any_of=["US"],
        axe_include_segment="x8dj3k",
        axe_exclude_segment="y9kl4m",
    )

    result = manager.build_targeting(targeting_overlay)

    # Verify both positive and negative custom targeting were set
    assert "customTargeting" in result
    assert "axe_segment" in result["customTargeting"]
    assert result["customTargeting"]["axe_segment"] == "x8dj3k"
    assert "NOT_axe_segment" in result["customTargeting"]
    assert result["customTargeting"]["NOT_axe_segment"] == "y9kl4m"


def test_axe_segments_combine_with_other_custom_targeting():
    """Test that AXE segments combine with other custom targeting."""
    manager = GAMTargetingManager()

    targeting_overlay = Targeting(
        geo_country_any_of=["US"],
        axe_include_segment="x8dj3k",
        custom={"gam": {"key_values": {"custom_key1": "value1", "custom_key2": "value2"}}},
    )

    result = manager.build_targeting(targeting_overlay)

    # Verify all custom targeting is present
    assert "customTargeting" in result
    assert "axe_segment" in result["customTargeting"]
    assert result["customTargeting"]["axe_segment"] == "x8dj3k"
    assert "custom_key1" in result["customTargeting"]
    assert result["customTargeting"]["custom_key1"] == "value1"
    assert "custom_key2" in result["customTargeting"]
    assert result["customTargeting"]["custom_key2"] == "value2"


def test_axe_segments_optional():
    """Test that AXE segments are optional and don't affect other targeting."""
    manager = GAMTargetingManager()

    targeting_overlay = Targeting(
        geo_country_any_of=["US"],
        # No axe_include_segment or axe_exclude_segment
    )

    result = manager.build_targeting(targeting_overlay)

    # Verify geo targeting is present but no custom targeting for AXE
    assert "geoTargeting" in result
    # customTargeting may or may not be present depending on other fields
