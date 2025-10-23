"""Unit tests for update_media_buy affected_packages response."""

from src.core.schemas import UpdateMediaBuyResponse


def test_affected_packages_includes_creative_assignment_details():
    """Test that affected_packages contains proper PackageUpdateResult structure."""
    # This test verifies the structure matches AdCP spec
    affected_packages = [
        {
            "buyer_package_ref": "pkg_default",
            "changes_applied": {
                "creative_ids": {
                    "added": ["creative_1", "creative_2"],
                    "removed": [],
                    "current": ["creative_1", "creative_2"],
                }
            },
        }
    ]

    response = UpdateMediaBuyResponse(
        media_buy_id="test_buy_123",
        buyer_ref="buyer_ref_123",
        affected_packages=affected_packages,
    )

    # Verify structure
    assert response.media_buy_id == "test_buy_123"
    assert response.buyer_ref == "buyer_ref_123"
    assert response.affected_packages is not None
    assert len(response.affected_packages) == 1

    # Check PackageUpdateResult structure
    package_result = response.affected_packages[0]
    assert package_result["buyer_package_ref"] == "pkg_default"
    assert "changes_applied" in package_result
    assert "creative_ids" in package_result["changes_applied"]

    # Check creative_ids changes structure
    creative_changes = package_result["changes_applied"]["creative_ids"]
    assert "added" in creative_changes
    assert "removed" in creative_changes
    assert "current" in creative_changes
    assert set(creative_changes["added"]) == {"creative_1", "creative_2"}
    assert creative_changes["removed"] == []
    assert set(creative_changes["current"]) == {"creative_1", "creative_2"}


def test_affected_packages_can_be_empty():
    """Test that affected_packages can be empty for non-creative updates."""
    response = UpdateMediaBuyResponse(
        media_buy_id="test_buy_456",
        buyer_ref="buyer_ref_456",
        affected_packages=[],
    )

    assert response.affected_packages is not None
    assert len(response.affected_packages) == 0


def test_affected_packages_shows_replaced_creatives():
    """Test that affected_packages shows both added and removed creatives."""
    affected_packages = [
        {
            "buyer_package_ref": "pkg_default",
            "changes_applied": {
                "creative_ids": {
                    "added": ["creative_2", "creative_3"],
                    "removed": ["creative_1"],
                    "current": ["creative_2", "creative_3"],
                }
            },
        }
    ]

    response = UpdateMediaBuyResponse(
        media_buy_id="test_buy_789",
        buyer_ref="buyer_ref_789",
        affected_packages=affected_packages,
    )

    creative_changes = response.affected_packages[0]["changes_applied"]["creative_ids"]
    assert set(creative_changes["added"]) == {"creative_2", "creative_3"}
    assert set(creative_changes["removed"]) == {"creative_1"}
    assert set(creative_changes["current"]) == {"creative_2", "creative_3"}


def test_response_serialization_includes_affected_packages():
    """Test that UpdateMediaBuyResponse serializes affected_packages correctly."""
    response = UpdateMediaBuyResponse(
        media_buy_id="test_buy_serialization",
        buyer_ref="buyer_ref_serialization",
        affected_packages=[
            {
                "buyer_package_ref": "pkg_1",
                "changes_applied": {
                    "creative_ids": {
                        "added": ["creative_a"],
                        "removed": [],
                        "current": ["creative_a"],
                    }
                },
            }
        ],
    )

    # Serialize to dict (as would happen when returning from API)
    response_dict = response.model_dump()

    assert "affected_packages" in response_dict
    assert len(response_dict["affected_packages"]) == 1
    assert response_dict["affected_packages"][0]["buyer_package_ref"] == "pkg_1"
    assert "changes_applied" in response_dict["affected_packages"][0]
