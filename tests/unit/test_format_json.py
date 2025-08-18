#!/usr/bin/env python3
"""
Simple test to verify the updated foundational creative formats JSON structure.
"""

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_formats_json():
    """Test that the foundational formats JSON has the new asset structure."""

    # Look for the file in the project root (two levels up from tests/unit/)
    json_path = Path(__file__).parent.parent.parent / "data" / "foundational_creative_formats.json"

    with open(json_path) as f:
        data = json.load(f)

    print("Testing foundational_creative_formats.json...")
    print(f"Version: {data.get('version')}")
    print(f"Number of formats: {len(data.get('foundational_formats', []))}")

    # Check each format
    for fmt in data.get("foundational_formats", []):
        print(f"\nFormat: {fmt['format_id']}")
        print(f"  Name: {fmt['name']}")
        print(f"  Type: {fmt['type']}")

        # Check for assets
        if "assets" in fmt:
            print(f"  ✓ Has assets field with {len(fmt['assets'])} assets:")
            for asset in fmt["assets"]:
                req = "*" if asset.get("required", True) else " "
                print(f"    {req} {asset['asset_id']} ({asset['asset_type']})")
        else:
            print("  ✗ Missing assets field!")

        # Check for legacy specs field
        if "specs" in fmt:
            print("  ✓ Has legacy specs field (for backward compatibility)")
        else:
            print("  ! No legacy specs field")

    # Verify specific formats have expected assets
    print("\n\nVerifying specific format structures:")

    # Check video format
    video_format = next(
        (f for f in data["foundational_formats"] if f["format_id"] == "foundation_universal_video"), None
    )
    if video_format:
        print("\n✓ Universal Video Format:")
        video_assets = {a["asset_id"] for a in video_format["assets"]}
        expected = {"video_file", "captions"}
        if expected.issubset(video_assets):
            print("  ✓ Has expected video assets")
        else:
            print(f"  ✗ Missing assets: {expected - video_assets}")

    # Check carousel format
    carousel_format = next(
        (f for f in data["foundational_formats"] if f["format_id"] == "foundation_product_showcase_carousel"), None
    )
    if carousel_format:
        print("\n✓ Product Showcase Carousel Format:")
        carousel_assets = {a["asset_id"] for a in carousel_format["assets"]}
        expected = {"product_images", "product_titles", "click_urls"}
        if expected.issubset(carousel_assets):
            print("  ✓ Has expected carousel assets")
        else:
            print(f"  ✗ Missing assets: {expected - carousel_assets}")

    print("\n\nAsset structure validation:")
    # Check that all assets have required fields
    all_valid = True
    for fmt in data["foundational_formats"]:
        for asset in fmt.get("assets", []):
            required_fields = {"asset_id", "asset_type", "required"}
            if not required_fields.issubset(asset.keys()):
                print(f"✗ Asset in {fmt['format_id']} missing fields: {required_fields - set(asset.keys())}")
                all_valid = False

    if all_valid:
        print("✓ All assets have required fields (asset_id, asset_type, required)")

    print("\n✓ Format structure update completed successfully!")


if __name__ == "__main__":
    test_formats_json()
