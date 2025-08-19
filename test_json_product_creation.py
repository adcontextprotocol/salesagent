#!/usr/bin/env python3
"""Quick test to verify product creation with JSON fields works."""

import sys

from database_session import get_db_session
from models import Product, Tenant


def test_product_creation():
    """Test creating a product with JSON fields."""

    with get_db_session() as session:
        # Clean up any existing test data
        session.query(Product).filter_by(product_id="test_json_product").delete()
        session.commit()

        # Ensure we have a tenant
        tenant = session.query(Tenant).filter_by(tenant_id="default").first()
        if not tenant:
            print("Error: No default tenant found")
            return False

        print(f"Creating product for tenant: {tenant.name}")

        # Create product with JSON fields as Python objects (not strings)
        # formats must be a list of format objects, not just IDs
        formats = [
            {
                "format_id": "display_300x250",
                "name": "Medium Rectangle",
                "type": "display",
                "description": "Standard 300x250 display ad",
                "width": 300,
                "height": 250,
            },
            {
                "format_id": "display_728x90",
                "name": "Leaderboard",
                "type": "display",
                "description": "Standard 728x90 display ad",
                "width": 728,
                "height": 90,
            },
            {
                "format_id": "video_16x9",
                "name": "Widescreen Video",
                "type": "video",
                "description": "16:9 aspect ratio video ad",
                "duration": 30,
            },
        ]

        product = Product(
            tenant_id="default",
            product_id="test_json_product",
            name="Test JSON Product",
            description="Testing JSON field handling",
            formats=formats,  # List of format objects
            countries=["US", "GB", "CA"],  # List, not JSON string
            price_guidance={"min": 5.0, "max": 15.0},  # Dict, not JSON string
            delivery_type="guaranteed",
            is_fixed_price=True,
            cpm=10.0,
            targeting_template={"geo_country_any_of": ["US", "GB"]},  # Dict, not JSON string
            implementation_config={"test_mode": True},  # Dict, not JSON string
        )

        try:
            session.add(product)
            session.commit()
            print("✅ Product created successfully!")

            # Verify it was stored correctly
            saved_product = session.query(Product).filter_by(product_id="test_json_product").first()

            # Check that JSON fields are proper Python types, not strings
            assert isinstance(saved_product.formats, list), f"formats should be list, got {type(saved_product.formats)}"
            assert isinstance(
                saved_product.countries, list
            ), f"countries should be list, got {type(saved_product.countries)}"
            assert isinstance(
                saved_product.price_guidance, dict
            ), f"price_guidance should be dict, got {type(saved_product.price_guidance)}"
            assert isinstance(
                saved_product.targeting_template, dict
            ), f"targeting_template should be dict, got {type(saved_product.targeting_template)}"
            assert isinstance(
                saved_product.implementation_config, dict
            ), f"implementation_config should be dict, got {type(saved_product.implementation_config)}"

            # Check values
            format_ids = [f["format_id"] for f in saved_product.formats]
            assert "display_300x250" in format_ids
            assert "display_728x90" in format_ids
            assert "US" in saved_product.countries
            assert saved_product.price_guidance["min"] == 5.0
            # targeting_template might be modified by validation, just check it exists
            assert isinstance(saved_product.targeting_template, dict)

            print("✅ All JSON fields stored and retrieved correctly!")
            print(f"  - Formats: {saved_product.formats}")
            print(f"  - Countries: {saved_product.countries}")
            print(f"  - Price guidance: {saved_product.price_guidance}")
            print(f"  - Targeting: {saved_product.targeting_template}")
            print(f"  - Config: {saved_product.implementation_config}")

            # Clean up
            session.delete(saved_product)
            session.commit()

            return True

        except Exception as e:
            session.rollback()
            print(f"❌ Error creating product: {e}")
            import traceback

            traceback.print_exc()
            return False


if __name__ == "__main__":
    success = test_product_creation()
    sys.exit(0 if success else 1)
