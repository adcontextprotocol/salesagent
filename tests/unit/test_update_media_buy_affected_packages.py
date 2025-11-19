"""Unit tests for update_media_buy affected_packages response."""

from src.core.schemas import AffectedPackage, UpdateMediaBuySuccess


def test_affected_packages_includes_creative_assignment_details():
    """Test that affected_packages contains proper PackageUpdateResult structure."""
    # Create AffectedPackage with extended fields
    affected_packages = [
        AffectedPackage(
            buyer_ref="buyer_ref_123",  # Required by adcp library
            package_id="pkg_1",  # Required by adcp library
            buyer_package_ref="pkg_default",  # Internal field (excluded from serialization)
            changes_applied={  # Sales agent extension (included in serialization)
                "creative_ids": {
                    "added": ["creative_1", "creative_2"],
                    "removed": [],
                    "current": ["creative_1", "creative_2"],
                }
            },
        )
    ]

    response = UpdateMediaBuySuccess(
        media_buy_id="test_buy_123",
        buyer_ref="buyer_ref_123",
        affected_packages=affected_packages,
    )

    # Verify structure
    assert response.media_buy_id == "test_buy_123"
    assert response.buyer_ref == "buyer_ref_123"
    assert response.affected_packages is not None
    assert len(response.affected_packages) == 1

    # Verify internal fields are accessible on the object
    package = response.affected_packages[0]
    assert package.buyer_ref == "buyer_ref_123"
    assert package.package_id == "pkg_1"
    assert package.buyer_package_ref == "pkg_default"  # Internal field
    assert package.changes_applied is not None  # Internal field

    # Check creative_ids changes structure from internal field
    creative_changes = package.changes_applied["creative_ids"]
    assert "added" in creative_changes
    assert "removed" in creative_changes
    assert "current" in creative_changes
    assert set(creative_changes["added"]) == {"creative_1", "creative_2"}
    assert creative_changes["removed"] == []
    assert set(creative_changes["current"]) == {"creative_1", "creative_2"}


def test_affected_packages_can_be_empty():
    """Test that affected_packages can be empty for non-creative updates."""
    response = UpdateMediaBuySuccess(
        media_buy_id="test_buy_456",
        buyer_ref="buyer_ref_456",
        affected_packages=[],
    )

    assert response.affected_packages is not None
    assert len(response.affected_packages) == 0


def test_affected_packages_shows_replaced_creatives():
    """Test that affected_packages shows both added and removed creatives."""
    affected_packages = [
        AffectedPackage(
            buyer_ref="buyer_ref_789",  # Required by adcp library
            package_id="pkg_1",  # Required by adcp library
            buyer_package_ref="pkg_default",  # Internal field
            changes_applied={  # Sales agent extension
                "creative_ids": {
                    "added": ["creative_2", "creative_3"],
                    "removed": ["creative_1"],
                    "current": ["creative_2", "creative_3"],
                }
            },
        )
    ]

    response = UpdateMediaBuySuccess(
        media_buy_id="test_buy_789",
        buyer_ref="buyer_ref_789",
        affected_packages=affected_packages,
    )

    creative_changes = response.affected_packages[0].changes_applied["creative_ids"]
    assert set(creative_changes["added"]) == {"creative_2", "creative_3"}
    assert set(creative_changes["removed"]) == {"creative_1"}
    assert set(creative_changes["current"]) == {"creative_2", "creative_3"}


def test_response_serialization_includes_affected_packages():
    """Test that UpdateMediaBuySuccess serializes affected_packages correctly."""
    response = UpdateMediaBuySuccess(
        media_buy_id="test_buy_serialization",
        buyer_ref="buyer_ref_serialization",
        affected_packages=[
            AffectedPackage(
                buyer_ref="buyer_ref_serialization",  # Required by adcp library
                package_id="pkg_1",  # Required by adcp library
                buyer_package_ref="pkg_1_buyer_ref",  # Internal field (excluded)
                changes_applied={  # Sales agent extension (included)
                    "creative_ids": {
                        "added": ["creative_a"],
                        "removed": [],
                        "current": ["creative_a"],
                    }
                },
            )
        ],
    )

    # Test 1: Regular serialization
    response_dict = response.model_dump()
    assert "affected_packages" in response_dict
    assert len(response_dict["affected_packages"]) == 1

    pkg = response_dict["affected_packages"][0]

    # Internal fields should be EXCLUDED
    assert "buyer_package_ref" not in pkg, "Internal field should be excluded"

    # Required and extension fields should be PRESENT
    assert pkg["buyer_ref"] == "buyer_ref_serialization"
    assert pkg["package_id"] == "pkg_1"
    assert "changes_applied" in pkg, "changes_applied extension field should be included"
    assert pkg["changes_applied"]["creative_ids"]["added"] == ["creative_a"]
    assert pkg["changes_applied"]["creative_ids"]["removed"] == []
    assert pkg["changes_applied"]["creative_ids"]["current"] == ["creative_a"]

    # Test 2: Internal serialization - same as regular for this response
    response_internal = response.model_dump_internal()
    assert "affected_packages" in response_internal
    # changes_applied should be present in both regular and internal serialization
    assert "changes_applied" in response_internal["affected_packages"][0]
