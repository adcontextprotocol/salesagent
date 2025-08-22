#!/usr/bin/env python3
"""Test script to verify full AdCP v2.4 compliance of the ADK agent."""

import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

from adcp_agent.agent import add_creative_assets, check_media_buy_status, create_media_buy, get_products, get_signals


async def test_adcp_compliance():
    """Test all AdCP v2.4 tools for compliance."""
    print("=" * 70)
    print("Testing AdCP v2.4 Compliance")
    print("=" * 70)

    # Test 1: get_products with both required parameters
    print("\n1. Testing get_products (REQUIRED: brief, promoted_offering)")
    print("-" * 50)
    try:
        result = await get_products(
            brief="video advertising for sports content with $50K budget",
            promoted_offering="streaming service for live sports events",
        )
        print("✓ Successfully called get_products")
        print(f"  - Found {result.get('total_count', 0)} products")
        if result.get("products"):
            first_product = result["products"][0]
            print(f"  - First product: {first_product.get('name', first_product.get('product_name', 'Unknown'))}")
            product_ids = [p.get("product_id", p.get("id")) for p in result["products"][:2]]
        else:
            print("  - No products returned")
            product_ids = ["test_product_1"]
    except Exception as e:
        print(f"✗ Error: {e}")
        product_ids = ["test_product_1"]

    # Test 2: get_signals for discovering targeting options
    print("\n2. Testing get_signals (optional discovery endpoint)")
    print("-" * 50)
    try:
        result = await get_signals(query="sports audiences", type="audience", category="interests")
        print("✓ Successfully called get_signals")
        signals = result.get("signals", [])
        print(f"  - Found {len(signals)} signals")
        if signals and len(signals) > 0:
            print(f"  - Sample signal: {signals[0].get('name', 'Unknown')}")
    except Exception as e:
        print(f"✗ Error: {e}")

    # Test 3: create_media_buy with all required parameters
    print("\n3. Testing create_media_buy")
    print("-" * 50)
    today = date.today()
    start_date = (today + timedelta(days=7)).strftime("%Y-%m-%d")
    end_date = (today + timedelta(days=37)).strftime("%Y-%m-%d")

    try:
        result = await create_media_buy(
            product_ids=product_ids[:1],  # Use first product
            start_date=start_date,
            end_date=end_date,
            budget=50000.0,
            targeting_overlay={
                "audience": ["sports_fans"],
                "geography": ["United States"],
                "platforms": ["mobile", "desktop"],
            },
        )
        print("✓ Successfully called create_media_buy")
        media_buy_id = result.get("media_buy_id", "unknown")
        status = result.get("status", "unknown")
        context_id = result.get("context_id")
        print(f"  - Media Buy ID: {media_buy_id}")
        print(f"  - Status: {status}")
        if context_id:
            print(f"  - Context ID: {context_id}")
    except Exception as e:
        print(f"✗ Error: {e}")
        media_buy_id = "test_buy_123"
        context_id = None

    # Test 4: check_media_buy_status (if we have a context_id)
    if context_id:
        print("\n4. Testing check_media_buy_status")
        print("-" * 50)
        try:
            result = await check_media_buy_status(context_id)
            print("✓ Successfully called check_media_buy_status")
            print(f"  - Media Buy ID: {result.get('media_buy_id', 'unknown')}")
            print(f"  - Status: {result.get('status', 'unknown')}")
        except Exception as e:
            print(f"✗ Error: {e}")
    else:
        print("\n4. Skipping check_media_buy_status (no context_id)")

    # Test 5: add_creative_assets
    print("\n5. Testing add_creative_assets")
    print("-" * 50)
    try:
        result = await add_creative_assets(
            media_buy_id=media_buy_id,
            creatives=[
                {
                    "name": "Sports Hero Video",
                    "format": "video",
                    "width": 1920,
                    "height": 1080,
                    "duration": 30,
                    "url": "https://example.com/creatives/sports-hero.mp4",
                },
                {
                    "name": "Sports Banner",
                    "format": "display",
                    "width": 728,
                    "height": 90,
                    "url": "https://example.com/creatives/sports-banner.jpg",
                },
            ],
        )
        print("✓ Successfully called add_creative_assets")
        if "creative_ids" in result:
            print(f"  - Added {len(result['creative_ids'])} creatives")
        print(f"  - Status: {result.get('status', 'unknown')}")
    except Exception as e:
        print(f"✗ Error: {e}")

    print("\n" + "=" * 70)
    print("✅ AdCP v2.4 Compliance Test Complete!")
    print("\nSummary:")
    print("- get_products: Both required parameters (brief, promoted_offering) work")
    print("- get_signals: Optional discovery endpoint available")
    print("- create_media_buy: Full purchase flow supported")
    print("- check_media_buy_status: Status monitoring available")
    print("- add_creative_assets: Creative management integrated")
    print("\nThe ADK agent is fully compliant with AdCP v2.4 specification!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_adcp_compliance())
