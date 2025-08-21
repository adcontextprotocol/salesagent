#!/usr/bin/env python3
"""
Populate the database with foundational creative formats.

This script loads the foundational formats from the JSON file and
inserts them into the creative_formats table.
"""

from database_session import get_db_session
from foundational_formats import FoundationalFormatsManager

from src.core.database.models import CreativeFormat, Tenant


def populate_foundational_formats():
    """Populate the creative_formats table with foundational formats."""

    # Load foundational formats
    manager = FoundationalFormatsManager()
    formats = manager.list_foundational_formats()

    with get_db_session() as session:
        inserted = 0
        updated = 0

        for fmt in formats:
            # Check if format already exists
            existing = session.query(CreativeFormat).filter_by(format_id=fmt.format_id).first()

            if existing:
                # Update existing format
                existing.name = fmt.name
                existing.type = fmt.type
                existing.description = fmt.description
                existing.specs = fmt.specs
                existing.is_standard = fmt.is_standard
                existing.is_foundational = fmt.is_foundational
                updated += 1
                print(f"Updated: {fmt.format_id}")
            else:
                # Insert new format
                new_format = CreativeFormat(
                    format_id=fmt.format_id,
                    name=fmt.name,
                    type=fmt.type,
                    description=fmt.description,
                    specs=fmt.specs,
                    is_standard=fmt.is_standard,
                    is_foundational=fmt.is_foundational,
                )
                session.add(new_format)
                inserted += 1
                print(f"Inserted: {fmt.format_id}")

        session.commit()

        print("\nSummary:")
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
                "desktop": [{"width": 1125, "height": 600}, {"width": 970, "height": 600}],
                "tablet": {"width": 728, "height": 600},
                "mobile": {"width": 800, "height": 1400},
            },
            "additional_specs": {
                "image_count": "3-5",
                "headlines_per_slide": True,
                "character_limits": {"headline": 100, "descriptor_desktop": 210, "descriptor_mobile": 70},
            },
        },
    )

    # Save to database
    with get_db_session() as session:
        # Get a tenant ID for NYTimes (if exists)
        nytimes_tenant = session.query(Tenant).filter(Tenant.name.like("%Times%")).first()
        tenant_id = nytimes_tenant.tenant_id if nytimes_tenant else None

        if nyt_slideshow:
            # Check if already exists
            existing = session.query(CreativeFormat).filter_by(format_id=nyt_slideshow["format_id"]).first()

            if not existing:
                # Extract dimensions for width/height (use first desktop dimension)
                desktop_dims = nyt_slideshow["specs"].get("dimensions", {}).get("desktop", [{}])
                width = desktop_dims[0].get("width") if desktop_dims else None
                height = desktop_dims[0].get("height") if desktop_dims else None

                new_extension = CreativeFormat(
                    format_id=nyt_slideshow["format_id"],
                    tenant_id=tenant_id,
                    name=nyt_slideshow["name"],
                    type=nyt_slideshow["type"],
                    description=nyt_slideshow["description"],
                    width=width,
                    height=height,
                    specs=nyt_slideshow["specs"],
                    is_standard=False,
                    is_foundational=False,
                    extends=nyt_slideshow["extends"],
                    modifications=manager.extended_formats[nyt_slideshow["format_id"]].modifications,
                    source_url="https://advertising.nytimes.com/formats/display-formats/slideshow-flex-xl/",
                )
                session.add(new_extension)
                print(f"\nCreated example extension: {nyt_slideshow['name']}")

        session.commit()


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
