#!/usr/bin/env python3
"""Test script for the new product catalog provider system."""

import asyncio
import json
import os
from datetime import datetime
from typing import Any

# Test with different provider configurations
TEST_CONFIGS = {
    "database": {"provider": "database", "config": {}},
    "ai": {"provider": "ai", "config": {"model": "gemini-flash-latest", "max_products": 3, "temperature": 0.3}},
    "mcp": {
        "provider": "mcp",
        "config": {"upstream_url": "http://localhost:9000/mcp/", "tool_name": "get_products", "timeout": 10},
    },
}

# Test briefs
TEST_BRIEFS = [
    "I need to reach sports fans aged 25-44 with display ads during March Madness",
    "Looking for premium video inventory targeting news readers in major US cities",
    "Want to run a branding campaign for our new electric vehicle, targeting eco-conscious consumers",
    "Need high-frequency audio ads for a local restaurant promotion this weekend",
]


async def test_provider(provider_type: str, config: dict[str, Any], brief: str):
    """Test a specific provider configuration."""
    print(f"\n{'=' * 60}")
    print(f"Testing {provider_type} provider")
    print(f"Brief: {brief}")
    print(f"Config: {json.dumps(config, indent=2)}")
    print(f"{'=' * 60}")

    try:
        # Import here to ensure fresh imports
        from product_catalog_providers.factory import get_product_catalog_provider

        # Create mock tenant config
        tenant_config = {"product_catalog": config}

        # Get provider instance
        provider = await get_product_catalog_provider(tenant_id=f"test_{provider_type}", tenant_config=tenant_config)

        # Test get_products
        start_time = datetime.now()
        products = await provider.get_products(brief=brief, tenant_id="default", principal_id="test_principal")
        elapsed = (datetime.now() - start_time).total_seconds()

        print(f"\nResults ({elapsed:.2f}s):")
        print(f"Found {len(products)} products")

        for i, product in enumerate(products[:5], 1):
            print(f"\n{i}. {product.name} (ID: {product.product_id})")
            print(f"   {product.description}")
            print(f"   Formats: {[f.name for f in product.formats]}")
            print(f"   Delivery: {product.delivery_type}")
            if product.cpm:
                print(f"   CPM: ${product.cpm}")
            elif product.price_guidance:
                print(f"   Price: ${product.price_guidance.floor}-${product.price_guidance.p75}")

        return True

    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {str(e)}")
        return False


async def test_direct_providers():
    """Test providers directly without the factory."""
    print("\n" + "=" * 60)
    print("DIRECT PROVIDER TESTS")
    print("=" * 60)

    # Test database provider directly
    try:
        from product_catalog_providers.database import DatabaseProductCatalog

        db_provider = DatabaseProductCatalog({})
        products = await db_provider.get_products(brief="test brief", tenant_id="default", principal_id="test")
        print(f"\n✅ Database provider: {len(products)} products")
    except Exception as e:
        print(f"\n❌ Database provider error: {e}")

    # Test AI provider directly (if API key is set)
    if os.environ.get("GEMINI_API_KEY"):
        try:
            from product_catalog_providers.ai import AIProductCatalog

            ai_provider = AIProductCatalog({"model": "gemini-flash-latest", "max_products": 2})
            products = await ai_provider.get_products(brief="I need sports advertising", tenant_id="default")
            print(f"\n✅ AI provider: {len(products)} products")
        except Exception as e:
            print(f"\n❌ AI provider error: {e}")
    else:
        print("\n⚠️  Skipping AI provider test (no GEMINI_API_KEY)")


async def main():
    """Run all tests."""
    print("Product Catalog Provider Test Suite")
    print("===================================")

    # Test direct providers first
    await test_direct_providers()

    # Test each provider type with factory
    for brief in TEST_BRIEFS[:2]:  # Test first 2 briefs
        for provider_type, config in TEST_CONFIGS.items():
            if provider_type == "mcp":
                print("\n⚠️  Skipping MCP provider (requires upstream server)")
                continue

            if provider_type == "ai" and not os.environ.get("GEMINI_API_KEY"):
                print("\n⚠️  Skipping AI provider (no GEMINI_API_KEY)")
                continue

            success = await test_provider(provider_type, config, brief)
            if not success and provider_type == "database":
                print("\n⚠️  Database provider failed - check if database is initialized")
                break

        # Small delay between briefs
        await asyncio.sleep(1)

    # Cleanup
    from product_catalog_providers.factory import cleanup_providers

    await cleanup_providers()

    print("\n\nTest suite completed!")


if __name__ == "__main__":
    # Initialize database if needed
    from src.core.database.database import init_db

    init_db()

    # Run tests
    asyncio.run(main())
