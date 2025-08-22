#!/usr/bin/env python3
"""Test script for ADK agent with direct tool calls."""

import asyncio
import sys
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

from src.adk.adcp_agent.agent import ConversationAnalyzer, ProductRanker, get_products_direct


async def test_direct_calls():
    """Test the ADK agent's direct tool calls."""
    print("Testing ADK Agent with Direct Tool Calls\n")
    print("=" * 60)

    # Initialize the analyzers
    analyzer = ConversationAnalyzer()
    ranker = ProductRanker()

    # Test 1: Get products without a specific query
    print("\nTest 1: Get all products")
    print("-" * 40)
    try:
        products = await get_products_direct("general advertising inventory", "advertiser products")
        print(f"✓ Retrieved {len(products)} products")

        if products:
            print("\nFirst product details:")
            first_product = products[0]
            print(f"  - ID: {first_product.get('product_id', first_product.get('id', 'N/A'))}")
            print(f"  - Name: {first_product.get('product_name', first_product.get('name', 'N/A'))}")
            price_model = first_product.get("price_model", {})
            price = price_model.get("floor_price", 0) if isinstance(price_model, dict) else 0
            print(f"  - Price: ${price:,.2f}")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback

        traceback.print_exc()

    # Test 2: Get products with a specific brief
    print("\n\nTest 2: Get products for video ads")
    print("-" * 40)
    try:
        products = await get_products_direct("video ads for sports content", "sports advertiser")
        print(f"✓ Retrieved {len(products)} products for video ads")

        if products:
            print("\nMatching products:")
            for p in products[:3]:  # Show top 3
                name = p.get("product_name", p.get("name", "N/A"))
                desc = p.get("product_description", p.get("description", "N/A"))
                print(f"  - {name}: {desc[:50] if desc != 'N/A' else 'N/A'}...")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback

        traceback.print_exc()

    # Test 3: Test the ranking algorithm
    print("\n\nTest 3: Test product ranking")
    print("-" * 40)

    # Create mock conversation history
    mock_messages = [
        {"role": "user", "content": "I need video ads for my sports campaign"},
        {"role": "assistant", "content": "I can help you with video advertising for sports content."},
        {"role": "user", "content": "My budget is around $10,000 for this month"},
        {"role": "assistant", "content": "Great! Let me find suitable video ad products for your $10,000 budget."},
        {"role": "user", "content": "I'm targeting young adults interested in sports"},
    ]

    try:
        # Get products
        products = await get_products_direct("general advertising inventory", "advertiser products")

        if products:
            # Extract message contents for analyzer
            conversation_texts = [msg["content"] for msg in mock_messages]

            # Analyze conversation
            analysis = analyzer.analyze(conversation_texts)
            print("Conversation analysis:")
            print(f"  - Budget: ${analysis['budget_range'][0]:,.0f} - ${analysis['budget_range'][1]:,.0f}")
            print(f"  - Formats: {', '.join(analysis['format_preferences']) or 'Any'}")
            print(f"  - Audience: {', '.join(analysis['audience_signals']) or 'General'}")

            # Debug: Print the first product structure
            print("\nDebug - Product structure:")
            print(f"  Keys: {list(products[0].keys())}")

            # Rank products based on conversation
            ranked = ranker.rank(products, analysis)

            print(f"\n✓ Ranked {len(ranked)} products based on conversation")
            print("\nTop 3 ranked products:")
            for i, p in enumerate(ranked[:3], 1):
                # Use the correct field name
                name_field = "product_name" if "product_name" in p else ("name" if "name" in p else "N/A")
                product_name = p.get(name_field, "Unknown Product") if name_field != "N/A" else "Unknown Product"
                print(f"\n  {i}. {product_name}")
                print(f"     Score: {p.get('_relevance_score', 0)}")
                print(f"     Reason: {p.get('_recommendation_reason', 'N/A')}")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback

        traceback.print_exc()

    print("\n" + "=" * 60)
    print("Testing Complete!")


if __name__ == "__main__":
    asyncio.run(test_direct_calls())
