"""Comprehensive tests for AffectedPackage serialization across all update_media_buy scenarios."""

from src.core.schemas import UpdateMediaBuySuccess, create_affected_package


def test_creative_assignment_in_serialized_response():
    """Test that creative assignment details are included in serialized response."""
    # Use factory function
    pkg = create_affected_package(
        buyer_ref="buyer_123",
        package_id="pkg_1",
        changes_applied={
            "creative_ids": {
                "added": ["creative_1", "creative_2"],
                "removed": [],
                "current": ["creative_1", "creative_2"],
            }
        },
    )

    response = UpdateMediaBuySuccess(
        media_buy_id="mb_123",
        buyer_ref="buyer_123",
        affected_packages=[pkg],
    )

    # Serialize to dict (what clients receive)
    serialized = response.model_dump()

    # Verify changes_applied is present in serialized output
    assert "affected_packages" in serialized
    assert len(serialized["affected_packages"]) == 1

    pkg_dict = serialized["affected_packages"][0]
    assert "changes_applied" in pkg_dict, "changes_applied should be serialized"
    assert "creative_ids" in pkg_dict["changes_applied"]
    assert pkg_dict["changes_applied"]["creative_ids"]["added"] == ["creative_1", "creative_2"]
    assert pkg_dict["changes_applied"]["creative_ids"]["removed"] == []
    assert pkg_dict["changes_applied"]["creative_ids"]["current"] == ["creative_1", "creative_2"]


def test_creative_replacement_in_serialized_response():
    """Test that creative replacement details (added + removed) are serialized."""
    pkg = create_affected_package(
        buyer_ref="buyer_123",
        package_id="pkg_1",
        changes_applied={
            "creative_ids": {
                "added": ["creative_2", "creative_3"],
                "removed": ["creative_1"],
                "current": ["creative_2", "creative_3"],
            }
        },
    )

    response = UpdateMediaBuySuccess(
        media_buy_id="mb_123",
        buyer_ref="buyer_123",
        affected_packages=[pkg],
    )

    serialized = response.model_dump()
    pkg_dict = serialized["affected_packages"][0]

    assert "changes_applied" in pkg_dict
    creative_changes = pkg_dict["changes_applied"]["creative_ids"]
    assert set(creative_changes["added"]) == {"creative_2", "creative_3"}
    assert creative_changes["removed"] == ["creative_1"]
    assert set(creative_changes["current"]) == {"creative_2", "creative_3"}


def test_budget_changes_in_serialized_response():
    """Test that budget updates are included in serialized response."""
    pkg = create_affected_package(
        buyer_ref="buyer_123",
        package_id="pkg_1",
        changes_applied={
            "budget": {
                "updated": 5000.0,
                "currency": "USD",
            }
        },
    )

    response = UpdateMediaBuySuccess(
        media_buy_id="mb_123",
        buyer_ref="buyer_123",
        affected_packages=[pkg],
    )

    serialized = response.model_dump()
    pkg_dict = serialized["affected_packages"][0]

    assert "changes_applied" in pkg_dict
    assert "budget" in pkg_dict["changes_applied"]
    assert pkg_dict["changes_applied"]["budget"]["updated"] == 5000.0
    assert pkg_dict["changes_applied"]["budget"]["currency"] == "USD"


def test_targeting_changes_in_serialized_response():
    """Test that targeting overlay updates are included in serialized response."""
    pkg = create_affected_package(
        buyer_ref="buyer_123",
        package_id="pkg_1",
        changes_applied={
            "targeting": {
                "geo_targeting": {
                    "included_locations": ["US-CA", "US-NY"],
                }
            }
        },
    )

    response = UpdateMediaBuySuccess(
        media_buy_id="mb_123",
        buyer_ref="buyer_123",
        affected_packages=[pkg],
    )

    serialized = response.model_dump()
    pkg_dict = serialized["affected_packages"][0]

    assert "changes_applied" in pkg_dict
    assert "targeting" in pkg_dict["changes_applied"]
    assert "geo_targeting" in pkg_dict["changes_applied"]["targeting"]


def test_multiple_change_types_in_single_package():
    """Test that multiple types of changes can coexist in changes_applied."""
    pkg = create_affected_package(
        buyer_ref="buyer_123",
        package_id="pkg_1",
        changes_applied={
            "creative_ids": {
                "added": ["creative_1"],
                "removed": [],
                "current": ["creative_1"],
            },
            "budget": {
                "updated": 3000.0,
                "currency": "USD",
            },
            "targeting": {
                "device_type_any_of": ["desktop", "mobile"],
            },
        },
    )

    response = UpdateMediaBuySuccess(
        media_buy_id="mb_123",
        buyer_ref="buyer_123",
        affected_packages=[pkg],
    )

    serialized = response.model_dump()
    pkg_dict = serialized["affected_packages"][0]

    # Verify all change types are present
    assert "changes_applied" in pkg_dict
    assert "creative_ids" in pkg_dict["changes_applied"]
    assert "budget" in pkg_dict["changes_applied"]
    assert "targeting" in pkg_dict["changes_applied"]


def test_multiple_packages_with_different_changes():
    """Test that multiple packages can have different changes in same response."""
    pkg1 = create_affected_package(
        buyer_ref="buyer_123",
        package_id="pkg_1",
        changes_applied={
            "creative_ids": {
                "added": ["creative_1"],
                "removed": [],
                "current": ["creative_1"],
            }
        },
    )

    pkg2 = create_affected_package(
        buyer_ref="buyer_123",
        package_id="pkg_2",
        changes_applied={
            "budget": {
                "updated": 2000.0,
                "currency": "USD",
            }
        },
    )

    response = UpdateMediaBuySuccess(
        media_buy_id="mb_123",
        buyer_ref="buyer_123",
        affected_packages=[pkg1, pkg2],
    )

    serialized = response.model_dump()

    assert len(serialized["affected_packages"]) == 2

    # First package has creative changes
    pkg1_dict = serialized["affected_packages"][0]
    assert "creative_ids" in pkg1_dict["changes_applied"]
    assert "budget" not in pkg1_dict["changes_applied"]

    # Second package has budget changes
    pkg2_dict = serialized["affected_packages"][1]
    assert "budget" in pkg2_dict["changes_applied"]
    assert "creative_ids" not in pkg2_dict["changes_applied"]


def test_factory_function_sets_all_fields():
    """Test that factory function properly initializes all fields."""
    pkg = create_affected_package(
        buyer_ref="buyer_123",
        package_id="pkg_1",
        changes_applied={"creative_ids": {"added": [], "removed": [], "current": []}},
    )

    # Verify required fields
    assert pkg.buyer_ref == "buyer_123"
    assert pkg.package_id == "pkg_1"

    # Verify extension field
    assert pkg.changes_applied is not None
    assert "creative_ids" in pkg.changes_applied

    # Verify internal field is set (but will be excluded from serialization)
    assert pkg.buyer_package_ref == "pkg_1"


def test_empty_changes_applied_is_serialized():
    """Test that empty changes_applied dict is serialized (not None)."""
    pkg = create_affected_package(
        buyer_ref="buyer_123",
        package_id="pkg_1",
        changes_applied={},  # Empty but not None
    )

    response = UpdateMediaBuySuccess(
        media_buy_id="mb_123",
        buyer_ref="buyer_123",
        affected_packages=[pkg],
    )

    serialized = response.model_dump()
    pkg_dict = serialized["affected_packages"][0]

    # Empty dict should still be serialized (provides signal that update was processed)
    assert "changes_applied" in pkg_dict
    assert pkg_dict["changes_applied"] == {}


def test_none_changes_applied_is_omitted():
    """Test that None changes_applied is omitted from serialization (Pydantic default behavior)."""
    pkg = create_affected_package(
        buyer_ref="buyer_123",
        package_id="pkg_1",
        changes_applied=None,  # No changes
    )

    response = UpdateMediaBuySuccess(
        media_buy_id="mb_123",
        buyer_ref="buyer_123",
        affected_packages=[pkg],
    )

    serialized = response.model_dump()
    pkg_dict = serialized["affected_packages"][0]

    # Pydantic omits None values by default for optional fields
    # This is standard behavior and acceptable - clients can check presence
    assert "changes_applied" not in pkg_dict, "None values are omitted by Pydantic"

    # Required fields are still present
    assert "buyer_ref" in pkg_dict
    assert "package_id" in pkg_dict


def test_internal_fields_are_excluded():
    """Test that internal fields (buyer_package_ref) are NOT serialized."""
    pkg = create_affected_package(
        buyer_ref="buyer_123",
        package_id="pkg_1",
        changes_applied={"creative_ids": {"added": [], "removed": [], "current": []}},
    )

    # Verify internal field is set on object
    assert pkg.buyer_package_ref == "pkg_1"

    response = UpdateMediaBuySuccess(
        media_buy_id="mb_123",
        buyer_ref="buyer_123",
        affected_packages=[pkg],
    )

    serialized = response.model_dump()
    pkg_dict = serialized["affected_packages"][0]

    # Internal field should be excluded from serialization
    assert "buyer_package_ref" not in pkg_dict, "Internal field should not be serialized"

    # But extension field should be present
    assert "changes_applied" in pkg_dict, "Extension field should be serialized"
