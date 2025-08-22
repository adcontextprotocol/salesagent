#!/usr/bin/env python3
"""
Demo script showing the ADK agent making context-aware product recommendations.

This demonstrates how the ADK agent:
1. Analyzes conversation history
2. Calls AdCP tools directly (no MCP protocol)
3. Ranks products based on context
4. Returns personalized recommendations
"""

import asyncio
import sys
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

from adcp_agent.agent import ConversationAnalyzer, ProductRanker, get_products_direct


async def demo_adk_recommendations():
    """Demonstrate ADK agent making context-aware recommendations."""

    print("=" * 70)
    print("ADK Agent Demo: Context-Aware Product Recommendations")
    print("=" * 70)

    # Simulate a realistic conversation
    conversation = [
        "I'm planning a major advertising campaign for Q1 2025",
        "We're launching a new streaming service for sports fans",
        "Our target audience is 18-34 year olds who love live sports",
        "Budget is around $50,000 for the initial push",
        "We need high-impact video ads that can run during live games",
        "Looking for CTV and pre-roll video formats specifically",
        "Geographic focus on United States and Canada",
        "Need to drive app downloads and subscriptions",
    ]

    print("\n📊 Conversation Context:")
    print("-" * 40)
    for msg in conversation:
        print(f"  • {msg}")

    # Analyze the conversation
    analyzer = ConversationAnalyzer()
    analysis = analyzer.analyze(conversation)

    print("\n🔍 Conversation Analysis:")
    print("-" * 40)
    print(f"  Budget Range: ${analysis['budget_range'][0]:,.0f} - ${analysis['budget_range'][1]:,.0f}")
    print(f"  Formats: {', '.join(analysis['format_preferences']) or 'Any'}")
    print(f"  Audience: {', '.join(analysis['audience_signals']) or 'General'}")
    print(f"  Objectives: {', '.join(analysis['campaign_objectives']) or 'Brand awareness'}")
    print(f"  Geography: {', '.join(analysis['geographic_targets']) or 'Global'}")
    print(f"  Urgency: {analysis['urgency_level']}")

    # Get products directly from the database
    print("\n📦 Fetching Products...")
    print("-" * 40)
    products = await get_products_direct(brief="video advertising for sports streaming")
    print(f"  Found {len(products)} available products")

    # Rank products based on context
    ranker = ProductRanker()
    ranked_products = ranker.rank(products, analysis)

    print("\n🎯 Recommended Products (Ranked by Relevance):")
    print("-" * 40)

    for i, product in enumerate(ranked_products[:5], 1):
        name = product.get("name", product.get("product_name", "Unknown"))
        score = product.get("_relevance_score", 0)
        reason = product.get("_recommendation_reason", "General match")

        print(f"\n  {i}. {name}")
        print(f"     Relevance Score: {score}/100")
        print(f"     Why Recommended: {reason}")

        # Show formats if available
        formats = product.get("formats", [])
        if formats:
            format_types = [f.get("type", "unknown") for f in formats if isinstance(f, dict)]
            if format_types:
                print(f"     Formats: {', '.join(format_types)}")

        # Show price if available
        price_model = product.get("price_model", {})
        if isinstance(price_model, dict) and "floor_price" in price_model:
            print(f"     Starting Price: ${price_model['floor_price']:,.2f}")

    print("\n" + "=" * 70)
    print("✅ Demo Complete!")
    print("\nThis demonstrates how the ADK agent:")
    print("  1. Analyzes conversation context to understand buyer needs")
    print("  2. Directly calls AdCP tools without MCP protocol overhead")
    print("  3. Ranks products based on relevance to the conversation")
    print("  4. Provides transparent scoring and reasoning")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(demo_adk_recommendations())
