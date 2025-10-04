#!/usr/bin/env python3
"""
Demo script to showcase the updated list_creative_formats functionality.

This demonstrates the enhanced AdCP standard creative formats support.
"""

from src.core.schemas import FORMAT_REGISTRY


def main():
    """Demonstrate the consolidated creative formats."""
    print("=== Consolidated AdCP Creative Formats Support ===\n")

    # Show summary statistics
    formats_by_type = {}
    standard_count = 0
    foundational_count = 0

    for format_obj in FORMAT_REGISTRY.values():
        if format_obj.type not in formats_by_type:
            formats_by_type[format_obj.type] = []
        formats_by_type[format_obj.type].append(format_obj)

        if format_obj.is_standard:
            standard_count += 1
        if "foundation" in format_obj.format_id:
            foundational_count += 1

    print(f"📊 Total Formats: {len(FORMAT_REGISTRY)}")
    print(f"📋 Standard Formats: {standard_count}")
    print(f"🏗️ Foundational Formats: {foundational_count}")
    print(f"🎨 Custom Formats: {len(FORMAT_REGISTRY) - standard_count}")
    print(f"📱 Format Types: {len(formats_by_type)}")
    print()

    # Show breakdown by type
    for format_type, type_formats in sorted(formats_by_type.items()):
        print(f"🔸 {format_type.upper()} ({len(type_formats)} formats):")

        for fmt in sorted(type_formats, key=lambda x: x.name):
            # Show key details
            req_count = len(fmt.requirements or {})
            asset_count = len(fmt.assets_required or [])

            details = []
            if fmt.is_standard:
                details.append("Standard")
            if fmt.iab_specification:
                details.append(f"IAB: {fmt.iab_specification}")
            if req_count > 0:
                details.append(f"{req_count} requirements")
            if asset_count > 0:
                details.append(f"{asset_count} assets")

            detail_str = f" [{', '.join(details)}]" if details else ""
            print(f"   • {fmt.name}{detail_str}")
        print()

    # Show examples of different format categories
    print("=== Format Examples ===\n")

    example_formats = {
        "Classic IAB Display": "display_300x250",
        "Modern Video": "video_1920x1080",
        "Native with Assets": "native_feed",
        "Digital Out-of-Home": "dooh_billboard_landscape",
        "Rich Media": "rich_media_expandable",
        "Connected TV": "ctv_preroll",
        "Social Media": "social_story",
        "Foundational Format": "foundation_immersive_canvas",
    }

    for category, format_id in example_formats.items():
        if format_id in FORMAT_REGISTRY:
            fmt = FORMAT_REGISTRY[format_id]
            print(f"🎯 {category}: {fmt.name}")
            print(f"   ID: {fmt.format_id}")
            print(f"   Type: {fmt.type}")

            # Show key requirements
            if fmt.requirements:
                key_reqs = []
                req_dict = fmt.requirements or {}
                if "width" in req_dict and "height" in req_dict:
                    key_reqs.append(f"{req_dict['width']}x{req_dict['height']}")
                if "duration" in req_dict:
                    key_reqs.append(f"{req_dict['duration']}s duration")
                if "aspect_ratio" in req_dict:
                    key_reqs.append(f"{req_dict['aspect_ratio']} aspect ratio")

                if key_reqs:
                    print(f"   Requirements: {', '.join(key_reqs)}")

            # Show assets if applicable
            if fmt.assets_required:
                asset_types = [asset.asset_type for asset in fmt.assets_required]
                print(f"   Assets Required: {', '.join(asset_types)}")

            print()

    print("=== Integration Features ===")
    print("✅ AdCP Schema Compliant")
    print("✅ Consolidated Single-Source Registry")
    print("✅ Foundational Formats Integrated")
    print("✅ Comprehensive Asset Requirements")
    print("✅ IAB Specification Alignment")
    print("✅ Modern Format Types (DOOH, CTV, Social)")
    print("✅ Returns Full Format Objects (not just IDs)")
    print("✅ Specification Version Tracking")
    print()

    print("Run `list_creative_formats` via MCP to see these formats in action!")


if __name__ == "__main__":
    main()
