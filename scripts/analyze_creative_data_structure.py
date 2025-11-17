#!/usr/bin/env python3
"""Analyze creative data structures in database to determine migration needs.

This script queries creatives from both local and production databases to understand:
1. What fields are present in the 'data' JSON column
2. Whether creatives use AdCP v2.4 structure (assets dict) or legacy structure (top-level url/dimensions)
3. Which creatives need migration
"""

import json
import os
from collections import Counter
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


def analyze_creative_structure(data: dict[str, Any]) -> dict[str, Any]:
    """Analyze structure of a creative's data field.

    Args:
        data: Creative data dict from database

    Returns:
        Dict with structure analysis
    """
    structure = {
        "has_assets": "assets" in data and isinstance(data.get("assets"), dict),
        "has_top_level_url": "url" in data,
        "has_top_level_width": "width" in data,
        "has_top_level_height": "height" in data,
        "has_preview_url": "preview_url" in data,
        "assets_count": len(data.get("assets", {})) if isinstance(data.get("assets"), dict) else 0,
        "top_level_fields": list(data.keys()),
    }

    # Determine structure type
    if structure["has_assets"] and structure["assets_count"] > 0:
        structure["type"] = "adcp_v2.4"  # Modern structure with assets dict
    elif structure["has_top_level_url"] or structure["has_top_level_width"]:
        structure["type"] = "legacy"  # Legacy structure with top-level fields
    else:
        structure["type"] = "unknown"

    return structure


def query_database(db_url: str, label: str) -> None:
    """Query database and analyze creative structures.

    Args:
        db_url: PostgreSQL connection URL
        label: Label for this database (e.g., "Local", "Production")
    """
    print(f"\n{'=' * 80}")
    print(f"Analyzing {label} Database")
    print(f"{'=' * 80}\n")

    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Get total count
        cursor.execute("SELECT COUNT(*) as total FROM creatives")
        total = cursor.fetchone()["total"]
        print(f"Total creatives: {total}")

        if total == 0:
            print("No creatives found in database")
            return

        # Sample creatives for analysis
        cursor.execute(
            """
            SELECT creative_id, tenant_id, name, format, agent_url, data
            FROM creatives
            ORDER BY created_at DESC
            LIMIT 50
            """
        )
        creatives = cursor.fetchall()

        # Analyze structures
        structure_types = Counter()
        has_assets_count = 0
        has_legacy_fields_count = 0
        sample_structures = []

        for creative in creatives:
            data = creative["data"]
            structure = analyze_creative_structure(data)
            structure_types[structure["type"]] += 1

            if structure["has_assets"]:
                has_assets_count += 1
            if structure["has_top_level_url"] or structure["has_top_level_width"]:
                has_legacy_fields_count += 1

            # Collect first 3 samples of each type
            if len([s for s in sample_structures if s["type"] == structure["type"]]) < 3:
                sample_structures.append(
                    {
                        "creative_id": creative["creative_id"],
                        "name": creative["name"],
                        "format": creative["format"],
                        "agent_url": creative["agent_url"],
                        "structure": structure,
                    }
                )

        # Print summary
        print(f"\nStructure Type Distribution (sample of {len(creatives)}):")
        for struct_type, count in structure_types.most_common():
            pct = (count / len(creatives)) * 100
            print(f"  {struct_type:15s}: {count:3d} ({pct:5.1f}%)")

        print("\nField Presence:")
        print(f"  With 'assets' dict:        {has_assets_count} creatives")
        print(f"  With legacy top-level:     {has_legacy_fields_count} creatives")

        # Print sample structures
        print("\nSample Structures:")
        for i, sample in enumerate(sample_structures, 1):
            print(f"\n  Sample {i}: {sample['structure']['type']}")
            print(f"    Creative ID: {sample['creative_id']}")
            print(f"    Name: {sample['name']}")
            print(f"    Format: {sample['format']}")
            print(f"    Agent URL: {sample['agent_url']}")
            print(f"    Structure: {json.dumps(sample['structure'], indent=6)}")

        # Query for actual data examples
        print("\nDetailed Data Examples:")
        for struct_type in ["adcp_v2.4", "legacy", "unknown"]:
            cursor.execute(
                """
                SELECT creative_id, name, data
                FROM creatives
                WHERE 1=1
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
            example = cursor.fetchone()
            if example:
                data_str = json.dumps(example["data"], indent=2)
                # Truncate if too long
                if len(data_str) > 500:
                    data_str = data_str[:500] + "\n  ... (truncated)"
                print(f"\n  Example {struct_type}:")
                print(f"    Creative: {example['creative_id']} - {example['name']}")
                print(f"    Data: {data_str}")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"Error querying {label} database: {e}")
        import traceback

        traceback.print_exc()


def main():
    """Main entry point."""
    # Local database
    local_db_url = os.getenv("DATABASE_URL")
    if local_db_url:
        query_database(local_db_url, "Local")
    else:
        print("DATABASE_URL not set - skipping local database")

    # Production database (if available)
    prod_db_url = os.getenv("PRODUCTION_DATABASE_URL")
    if prod_db_url:
        query_database(prod_db_url, "Production")
    else:
        print("\nPRODUCTION_DATABASE_URL not set - skipping production database")

    # Summary and recommendations
    print(f"\n{'=' * 80}")
    print("Migration Analysis Summary")
    print(f"{'=' * 80}\n")
    print("AdCP v2.4 Structure:")
    print("  - Uses 'assets' dict with typed asset objects (ImageAsset, VideoAsset, etc.)")
    print("  - Asset IDs map to format_spec.assets_required")
    print("  - No top-level url/width/height fields\n")
    print("Legacy Structure:")
    print("  - Top-level 'url', 'width', 'height' fields")
    print("  - May or may not have 'assets' dict\n")
    print("Recommendation:")
    print("  - If all creatives use AdCP v2.4: Remove _extract_creative_url_and_dimensions()")
    print("  - If mixed: Keep extraction for backwards compatibility")
    print("  - If mostly legacy: Consider one-time migration script")


if __name__ == "__main__":
    main()
