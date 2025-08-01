#!/usr/bin/env python3
"""
Populate the database with foundational creative formats.

This script loads the foundational formats from the JSON file and
inserts them into the creative_formats table.
"""

import json
from pathlib import Path
from db_config import get_db_connection
from foundational_formats import FoundationalFormatsManager


def populate_foundational_formats():
    """Populate the creative_formats table with foundational formats."""
    
    # Load foundational formats
    manager = FoundationalFormatsManager()
    formats = manager.list_foundational_formats()
    
    conn = get_db_connection()
    
    inserted = 0
    updated = 0
    
    for fmt in formats:
        # Check if format already exists
        cursor = conn.execute(
            "SELECT format_id FROM creative_formats WHERE format_id = ?",
            (fmt.format_id,)
        )
        existing = cursor.fetchone()
        
        if existing:
            # Update existing format
            conn.execute("""
                UPDATE creative_formats
                SET name = ?, type = ?, description = ?, 
                    specs = ?, is_standard = ?, is_foundational = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE format_id = ?
            """, (
                fmt.name,
                fmt.type,
                fmt.description,
                json.dumps(fmt.specs),
                fmt.is_standard,
                fmt.is_foundational,
                fmt.format_id
            ))
            updated += 1
            print(f"Updated: {fmt.format_id}")
        else:
            # Insert new format
            conn.execute("""
                INSERT INTO creative_formats (
                    format_id, name, type, description, 
                    specs, is_standard, is_foundational
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                fmt.format_id,
                fmt.name,
                fmt.type,
                fmt.description,
                json.dumps(fmt.specs),
                fmt.is_standard,
                fmt.is_foundational
            ))
            inserted += 1
            print(f"Inserted: {fmt.format_id}")
    
    conn.connection.commit()
    conn.close()
    
    print(f"\nSummary:")
    print(f"  Inserted: {inserted} foundational formats")
    print(f"  Updated: {updated} foundational formats")
    print(f"  Total: {len(formats)} foundational formats")


def create_example_extensions():
    """Create example publisher extensions in the database."""
    
    manager = FoundationalFormatsManager()
    
    # Create NYTimes extension
    nyt_slideshow = manager.create_extension(
        format_id="nytimes_slideshow_flex_xl",
        extends="foundation_product_showcase_carousel",
        name="NYTimes Slideshow Flex XL",
        modifications={
            "dimensions": {
                "desktop": [
                    {"width": 1125, "height": 600},
                    {"width": 970, "height": 600}
                ],
                "tablet": {"width": 728, "height": 600},
                "mobile": {"width": 800, "height": 1400}
            },
            "additional_specs": {
                "image_count": "3-5",
                "headlines_per_slide": True,
                "character_limits": {
                    "headline": 100,
                    "descriptor_desktop": 210,
                    "descriptor_mobile": 70
                }
            }
        }
    )
    
    # Save to database
    conn = get_db_connection()
    
    # Get a tenant ID for NYTimes (if exists)
    cursor = conn.execute(
        "SELECT tenant_id FROM tenants WHERE name LIKE '%Times%' LIMIT 1"
    )
    result = cursor.fetchone()
    tenant_id = result['tenant_id'] if result else None
    
    if nyt_slideshow:
        # Check if already exists
        cursor = conn.execute(
            "SELECT format_id FROM creative_formats WHERE format_id = ?",
            (nyt_slideshow['format_id'],)
        )
        
        if not cursor.fetchone():
            # Extract dimensions for width/height (use first desktop dimension)
            width = nyt_slideshow['specs'].get('dimensions', {}).get('desktop', [{}])[0].get('width')
            height = nyt_slideshow['specs'].get('dimensions', {}).get('desktop', [{}])[0].get('height')
            
            conn.execute("""
                INSERT INTO creative_formats (
                    format_id, tenant_id, name, type, description,
                    width, height, specs, is_standard, is_foundational,
                    extends, modifications, source_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                nyt_slideshow['format_id'],
                tenant_id,
                nyt_slideshow['name'],
                nyt_slideshow['type'],
                nyt_slideshow['description'],
                width,
                height,
                json.dumps(nyt_slideshow['specs']),
                False,  # Not standard
                False,  # Not foundational
                nyt_slideshow['extends'],
                json.dumps(manager.extended_formats[nyt_slideshow['format_id']].modifications),
                "https://advertising.nytimes.com/formats/display-formats/slideshow-flex-xl/"
            ))
            print(f"\nCreated example extension: {nyt_slideshow['name']}")
    
    conn.connection.commit()
    conn.close()


def main():
    """Main entry point."""
    print("Populating Foundational Creative Formats")
    print("=" * 50)
    
    # First populate foundational formats
    populate_foundational_formats()
    
    # Then create example extensions
    print("\nCreating Example Extensions")
    print("=" * 50)
    create_example_extensions()
    
    print("\nDone!")


if __name__ == "__main__":
    main()