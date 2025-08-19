#!/usr/bin/env python3
"""
Examples of using foundational creative formats with publisher extensions.

This demonstrates how publishers can extend base formats while maintaining
standardization across the ecosystem.
"""

import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from foundational_formats import FoundationalFormatsManager


def create_nytimes_extensions(manager: FoundationalFormatsManager):
    """Create NYTimes-specific extensions of foundational formats."""

    print("\n=== Creating NYTimes Extensions ===")

    # 1. Extend Product Showcase Carousel for Slideshow Flex XL
    slideshow = manager.create_extension(
        format_id="nytimes_slideshow_flex_xl",
        extends="foundation_product_showcase_carousel",
        name="NYTimes Slideshow Flex XL",
        modifications={
            "dimensions": {
                "desktop": [{"width": 1125, "height": 600}, {"width": 970, "height": 600}],
                "tablet": {"width": 728, "height": 600},
                "mobile": {"width": 800, "height": 1400},
            },
            "additional_specs": {
                "image_count": "3-5",
                "headlines_per_slide": True,
                "descriptor_messages": True,
                "character_limits": {"headline": 100, "descriptor_desktop": 210, "descriptor_mobile": 70, "cta": 15},
                "logo_required": True,
                "logo_format": "transparent PNG or EPS",
            },
            "enhancements": {
                "split_screen_layout": True,
                "retina_display_support": True,
                "safe_zone_mobile": "100px all sides",
                "platforms": ["Desktop", "Tablet Web", "Mobile Web", "Mobile App"],
            },
        },
    )

    print(f"Created: {slideshow['name']} (extends {slideshow['extends']})")

    # 2. Extend Immersive Canvas for NYTimes Premium Display
    premium_display = manager.create_extension(
        format_id="nytimes_premium_display",
        extends="foundation_immersive_canvas",
        name="NYTimes Premium Display Canvas",
        modifications={
            "dimensions": {
                "desktop": {"width": 970, "height": 250},
                "tablet": {"width": 728, "height": 90},
                "mobile": {"width": 320, "height": 100},
            },
            "additional_specs": {
                "viewability_threshold": "50% for 1 second",
                "rich_media_support": True,
                "above_the_fold_placement": True,
            },
            "restrictions": {
                "animation": {"allowed": True, "max_duration_seconds": 15, "user_initiated_expansion": False}
            },
        },
    )

    print(f"Created: {premium_display['name']} (extends {premium_display['extends']})")

    return [slideshow, premium_display]


def create_yahoo_extensions(manager: FoundationalFormatsManager):
    """Create Yahoo-specific extensions of foundational formats."""

    print("\n=== Creating Yahoo Extensions ===")

    # 1. Extend Immersive Canvas for E2E Lighthouse
    e2e_lighthouse = manager.create_extension(
        format_id="yahoo_e2e_lighthouse",
        extends="foundation_immersive_canvas",
        name="Yahoo E2E Lighthouse",
        modifications={
            "dimensions": {
                "mobile": {
                    "static": {"width": 720, "height": 1280},
                    "full_bleed_video": {"width": 1080, "height": 1920},
                }
            },
            "additional_specs": {
                "aspect_ratio": "9:16",
                "format_variants": ["Static Image", "Video", "Full Bleed Video", "Carousel", "Video + Carousel"],
                "carousel_specs": {
                    "min_images": 2,
                    "max_images": 6,
                    "image_dimensions": {"width": 720, "height": 1280},
                },
                "video_carousel_specs": {"video_dimensions": "720x405 or 1920x1080", "carousel_dimensions": "720x875"},
            },
            "enhancements": {
                "mobile_only": True,
                "site_served": True,
                "backup_image_required": True,
                "autoplay_limit_seconds": 15,
            },
        },
    )

    print(f"Created: {e2e_lighthouse['name']} (extends {e2e_lighthouse['extends']})")

    # 2. Extend Universal Video for Yahoo Video Specs
    video_format = manager.create_extension(
        format_id="yahoo_premium_video",
        extends="foundation_universal_video",
        name="Yahoo Premium Video",
        modifications={
            "additional_specs": {
                "max_file_size_mb": 2.5,
                "aspect_ratios": ["16:9", "9:16"],
                "resolutions": {
                    "16:9": [{"width": 1920, "height": 1080}, {"width": 720, "height": 405}],
                    "9:16": [{"width": 1080, "height": 1920}, {"width": 720, "height": 1280}],
                },
            },
            "restrictions": {"duration_seconds": {"min": 6, "max": 15}},
            "enhancements": {"ssl_compliance_required": True, "ad_policy_compliance": "Yahoo Ad Policies"},
        },
    )

    print(f"Created: {video_format['name']} (extends {video_format['extends']})")

    return [e2e_lighthouse, video_format]


def demonstrate_compatibility_check(manager: FoundationalFormatsManager):
    """Show how to check if extensions are compatible."""

    print("\n=== Compatibility Checking ===")

    # Valid extension
    errors = manager.validate_extension(
        extends="foundation_product_showcase_carousel",
        modifications={
            "dimensions": {"desktop": {"width": 970, "height": 250}},
            "additional_specs": {"custom_feature": True},
        },
    )
    print(f"Valid extension check: {'PASS' if not errors else 'FAIL'}")

    # Invalid extension (trying to remove required specs)
    errors = manager.validate_extension(
        extends="foundation_universal_video",
        modifications={"restrictions": {"file_types": None}},  # Can't remove required spec
    )
    print(f"Invalid extension check: {'FAIL' if errors else 'PASS'}")
    if errors:
        for error in errors:
            print(f"  - {error}")


def suggest_base_format_demo(manager: FoundationalFormatsManager):
    """Demonstrate base format suggestion."""

    print("\n=== Base Format Suggestions ===")

    test_specs = [
        {"name": "Multi-product showcase", "specs": {"product_count": 5, "carousel": True}},
        {"name": "Expandable banner", "specs": {"expandable": True, "collapsed_state": {"width": 728, "height": 90}}},
        {"name": "Mobile scroll experience", "specs": {"scroll": True, "mobile_first": True, "parallax": True}},
        {"name": "Standard video", "specs": {"type": "video", "duration": 30}},
    ]

    for test in test_specs:
        suggested = manager.suggest_base_format(test["specs"])
        print(f"{test['name']}: {suggested or 'No match'}")


def main():
    """Run all examples."""

    # Initialize manager
    manager = FoundationalFormatsManager()

    # Show available foundational formats
    print("=== Available Foundational Formats ===")
    for fmt in manager.list_foundational_formats():
        print(f"- {fmt.format_id}: {fmt.name}")
        print(f"  Type: {fmt.type}")
        print(f"  Description: {fmt.description}")

    # Create publisher extensions
    create_nytimes_extensions(manager)
    create_yahoo_extensions(manager)

    # Demonstrate compatibility checking
    demonstrate_compatibility_check(manager)

    # Demonstrate base format suggestions
    suggest_base_format_demo(manager)

    # Export all formats
    print("\n=== Exporting All Formats ===")
    all_formats = manager.export_all_formats()

    # Save to file
    output_file = Path(__file__).parent / "all_formats_export.json"
    with open(output_file, "w") as f:
        json.dump(all_formats, f, indent=2)

    print(f"Exported {len(all_formats['foundational_formats'])} foundational formats")
    print(f"Exported {len(all_formats['extended_formats'])} extended formats")
    print(f"Saved to: {output_file}")

    # Show example of resolved format
    print("\n=== Example Resolved Format ===")
    if all_formats["extended_formats"]:
        example = all_formats["extended_formats"][0]["resolved"]
        print(f"Format: {example['name']}")
        print(f"Extends: {example['extends']}")
        print(f"Type: {example['type']}")
        print("Specs preview:")
        specs_str = json.dumps(example["specs"], indent=2)
        print(specs_str[:500] + "..." if len(specs_str) > 500 else specs_str)


if __name__ == "__main__":
    main()
