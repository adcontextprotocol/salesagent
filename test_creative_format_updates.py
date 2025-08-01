#!/usr/bin/env python3
"""
Test script for creative format updates to match AdCP spec changes.
"""

import json
from foundational_formats import FoundationalFormatsManager
from creative_format_converter import convert_legacy_format_to_assets
from schemas import Format, Asset, DeliveryOptions

def test_foundational_formats():
    """Test that foundational formats load correctly with assets."""
    print("Testing foundational formats...")
    
    manager = FoundationalFormatsManager()
    formats = manager.list_foundational_formats()
    
    print(f"Loaded {len(formats)} foundational formats")
    
    # Check that formats have assets
    for fmt in formats:
        print(f"\nFormat: {fmt.format_id}")
        print(f"  Name: {fmt.name}")
        print(f"  Type: {fmt.type}")
        print(f"  Assets: {len(fmt.assets)} assets")
        
        for asset in fmt.assets:
            print(f"    - {asset['asset_id']} ({asset['asset_type']}) {'*' if asset.get('required', True) else ''}")
    
    return True


def test_format_model():
    """Test the new Format model with assets."""
    print("\n\nTesting Format model...")
    
    # Create a video format with assets
    video_format = Format(
        format_id="video_15s_hosted",
        name="15-Second Hosted Video",
        type="video",
        description="15-second video for in-stream placement",
        assets=[
            Asset(
                asset_id="video_file",
                asset_type="video",
                required=True,
                name="Video File",
                description="Main video creative",
                acceptable_formats=["mp4", "webm"],
                max_file_size_mb=10,
                duration_seconds=15,
                max_bitrate_mbps=5
            ),
            Asset(
                asset_id="captions",
                asset_type="text",
                required=True,
                name="Captions",
                description="Caption file for accessibility",
                acceptable_formats=["srt", "vtt"]
            ),
            Asset(
                asset_id="companion_banner",
                asset_type="image",
                required=False,
                name="Companion Banner",
                description="Static companion display",
                acceptable_formats=["jpg", "png"],
                max_file_size_mb=0.2,
                width=300,
                height=250
            )
        ],
        delivery_options=DeliveryOptions(
            hosted={"delivery_method": "cdn"},
            vast={"version": "4.0"}
        )
    )
    
    print(f"Created format: {video_format.format_id}")
    print(f"Assets: {len(video_format.assets)}")
    for asset in video_format.assets:
        print(f"  - {asset.asset_id}: {asset.asset_type} {'(required)' if asset.required else '(optional)'}")
    
    # Test JSON serialization
    format_json = video_format.model_dump_json(indent=2)
    print(f"\nJSON representation:\n{format_json[:500]}...")
    
    return True


def test_legacy_conversion():
    """Test conversion from legacy format to new asset structure."""
    print("\n\nTesting legacy format conversion...")
    
    # Legacy video format
    legacy_format = {
        "format_id": "video_standard",
        "name": "Standard Video",
        "type": "video",
        "description": "Standard video format",
        "specs": {
            "aspect_ratios": ["16:9", "9:16"],
            "file_types": ["mp4", "webm"],
            "max_file_size_mb": 50,
            "duration_seconds": {
                "min": 6,
                "max": 30
            },
            "captions": {
                "required": True,
                "formats": ["srt", "vtt"]
            }
        }
    }
    
    print("Legacy format specs:")
    print(json.dumps(legacy_format["specs"], indent=2))
    
    # Convert to new format
    converted = convert_legacy_format_to_assets(legacy_format)
    
    print("\nConverted format with assets:")
    print(f"Assets: {len(converted['assets'])}")
    for asset in converted["assets"]:
        print(f"  - {asset['asset_id']}: {asset['asset_type']} {'(required)' if asset.get('required', True) else '(optional)'}")
        if "acceptable_formats" in asset:
            print(f"    Formats: {', '.join(asset['acceptable_formats'])}")
    
    return True


def test_carousel_format():
    """Test carousel format with new structure."""
    print("\n\nTesting carousel format...")
    
    manager = FoundationalFormatsManager()
    carousel_format = manager.get_foundational_format("foundation_product_showcase_carousel")
    
    if carousel_format:
        print(f"Carousel format: {carousel_format.name}")
        print(f"Assets:")
        for asset in carousel_format.assets:
            print(f"  - {asset['asset_id']}: {asset['asset_type']}")
            if 'additional_specs' in asset:
                print(f"    Specs: {json.dumps(asset['additional_specs'], indent=6)}")
    
    return True


def main():
    """Run all tests."""
    print("=== Creative Format Update Tests ===\n")
    
    tests = [
        test_foundational_formats,
        test_format_model,
        test_legacy_conversion,
        test_carousel_format
    ]
    
    passed = 0
    for test in tests:
        try:
            if test():
                passed += 1
                print(f"\n✓ {test.__name__} passed")
            else:
                print(f"\n✗ {test.__name__} failed")
        except Exception as e:
            print(f"\n✗ {test.__name__} failed with error: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n\n=== Results: {passed}/{len(tests)} tests passed ===")


if __name__ == "__main__":
    main()