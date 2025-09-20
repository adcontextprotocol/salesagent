#!/usr/bin/env python3
"""Debug script to trace the database provider product processing."""

import json
import sys
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.core.schemas import Product


def simulate_database_provider():
    """Simulate the database provider logic to find where formats field is lost."""

    # Simulate raw database product data (from the database query)
    raw_product_data = {
        "product_id": "prod_1",
        "name": "Premium Display - News",
        "description": None,  # This could be None from database
        "formats": ["display_300x250"],  # This is from the database
        "delivery_type": "guaranteed",
        "is_fixed_price": True,
        "cpm": 10.50,
        "price_guidance": {"min": 8.0, "max": 12.0},  # Will be removed
        "is_custom": None,  # Could be None
        "countries": ["US", "CA"],  # Will be removed
        "targeting_template": {"demographics": "adults"},  # Will be removed
        "implementation_config": {"placement_id": "123"},  # Will be removed
    }

    print("Step 1: Raw product data from database:")
    print(f"  {json.dumps(raw_product_data, indent=2)}")

    # Step 2: Handle JSONB fields (PostgreSQL returns them as Python objects, SQLite as strings)
    product_data = raw_product_data.copy()
    if product_data.get("formats"):
        if isinstance(product_data["formats"], str):
            product_data["formats"] = json.loads(product_data["formats"])
            print("  ✓ Parsed formats from JSON string")
        else:
            print("  ✓ Formats already a Python object")

    print("Step 2: After JSONB parsing:")
    print(f"  formats: {product_data.get('formats')} (type: {type(product_data.get('formats'))})")

    # Step 3: Remove internal fields that shouldn't be exposed to buyers
    product_data.pop("targeting_template", None)  # Internal targeting config
    product_data.pop("price_guidance", None)  # Not part of Product schema
    product_data.pop("implementation_config", None)  # Proprietary ad server config
    product_data.pop("countries", None)  # Not part of Product schema

    print("Step 3: After removing internal fields:")
    print(f"  formats still present: {'formats' in product_data}")
    print(f"  formats value: {product_data.get('formats')}")

    # Step 4: Fix missing required fields for Pydantic validation

    # 4.1: Fix missing description (required field)
    if not product_data.get("description"):
        product_data["description"] = f"Advertising product: {product_data.get('name', 'Unknown Product')}"
        print("  ✓ Fixed missing description")

    # 4.2: Fix missing is_custom (should default to False)
    if product_data.get("is_custom") is None:
        product_data["is_custom"] = False
        print("  ✓ Fixed missing is_custom")

    # 4.3: Convert formats to format IDs (strings) as expected by Product schema
    if product_data.get("formats"):
        print(f"  Step 4.3: Processing formats: {product_data['formats']} (type: {type(product_data['formats'])})")
        format_ids = []
        for i, format_obj in enumerate(product_data["formats"]):
            print(f"    Processing format {i}: {format_obj} (type: {type(format_obj)})")
            # Handle case where format_obj might be a string instead of dict
            if isinstance(format_obj, str):
                # Check if it's a JSON string first
                try:
                    parsed = json.loads(format_obj)
                    if isinstance(parsed, dict) and "format_id" in parsed:
                        # It's a format object with format_id
                        format_ids.append(parsed["format_id"])
                        print(f"      Extracted format_id from JSON string: {parsed['format_id']}")
                    else:
                        # It's just a format identifier string
                        format_ids.append(format_obj)
                        print(f"      Using string as format_id: {format_obj}")
                except (json.JSONDecodeError, TypeError):
                    # It's a plain string format identifier
                    format_ids.append(format_obj)
                    print(f"      Using plain string as format_id: {format_obj}")
            elif isinstance(format_obj, dict):
                # It's a format object, extract the format_id
                format_id = format_obj.get("format_id")
                if format_id:
                    format_ids.append(format_id)
                    print(f"      Extracted format_id from dict: {format_id}")
                else:
                    # Try to construct format_id from other fields
                    name = format_obj.get("name", "unknown_format")
                    format_ids.append(name)
                    print(f"      Using name as format_id: {name}")
            else:
                print(f"      WARNING: Skipping unexpected format type: {type(format_obj)} - {format_obj}")
                continue

        product_data["formats"] = format_ids
        print(f"  Final converted formats: {format_ids}")

    print("Step 4: After format processing:")
    print(f"  formats present: {'formats' in product_data}")
    print(f"  formats value: {product_data.get('formats')}")

    # Step 5: Convert DECIMAL fields to float
    if product_data.get("cpm") is not None:
        try:
            product_data["cpm"] = float(product_data["cpm"])
            print("  ✓ Converted cpm to float")
        except (ValueError, TypeError) as e:
            print(f"  ⚠️ Failed to convert cpm to float: {e}")
            product_data["cpm"] = None

    print("Step 5: Final product data before validation:")
    print(f"  {json.dumps(product_data, indent=2)}")

    # Step 6: Validate against AdCP protocol schema
    try:
        validated_product = Product(**product_data)
        print("✅ Product validation succeeded!")
        print(f"Validated product model_dump: {validated_product.model_dump()}")
        return validated_product
    except Exception as e:
        print(f"❌ Product validation failed: {e}")
        print(f"Product data that failed: {product_data}")
        return None


if __name__ == "__main__":
    simulate_database_provider()
