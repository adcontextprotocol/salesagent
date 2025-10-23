#!/usr/bin/env python3
"""Test script to directly call the product catalog provider."""

import asyncio
import logging
import sys
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

from product_catalog_providers.database import DatabaseProductCatalog


async def test_product_provider():
    """Test the database product catalog provider directly."""

    print("Testing DatabaseProductCatalog directly...")

    # Create database provider
    provider = DatabaseProductCatalog({})

    # Initialize it
    await provider.initialize()

    try:
        # Call get_products directly
        products = await provider.get_products(
            brief="Discover available advertising products for testing",
            tenant_id="default",
            principal_id="test_principal",
            context={
                "brand_manifest": {"name": "gourmet robot food"},
                "tenant_id": "default",
                "principal_id": "test_principal",
            },
            principal_data={"principal_id": "test_principal", "name": "Test Principal", "platform_mappings": {}},
        )

        print("✅ DatabaseProductCatalog.get_products call succeeded!")
        print(f"Number of products: {len(products)}")

        for i, product in enumerate(products):
            print(f"Product {i}: {type(product)} - {product.model_dump()}")

    except Exception as e:
        print(f"❌ DatabaseProductCatalog.get_products call failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_product_provider())
