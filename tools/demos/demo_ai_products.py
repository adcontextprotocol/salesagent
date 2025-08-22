#!/usr/bin/env python3
"""Demo script to show AI product features working."""

import os

from default_products import get_default_products, get_industry_specific_products


def demo_product_features():
    print("=== AdCP AI Product Features Demo ===\n")

    # 1. Show default products
    print("1. Default Products (automatically created for new tenants):")
    print("-" * 60)

    default_products = get_default_products()
    for product in default_products:
        pricing = (
            f"${product['cpm']} CPM"
            if product["cpm"]
            else f"${product['price_guidance']['min']}-${product['price_guidance']['max']} CPM"
        )
        print(f"  • {product['name']} ({product['delivery_type']})")
        print(f"    ID: {product['product_id']}")
        print(f"    Pricing: {pricing}")
        print(f"    Formats: {', '.join(product['formats'][:3])}")
        print()

    # 2. Show industry templates
    print("\n2. Industry-Specific Templates:")
    print("-" * 60)

    for industry in ["news", "sports", "entertainment", "ecommerce"]:
        products = get_industry_specific_products(industry)
        # Get only the industry-specific ones
        default_ids = {p["product_id"] for p in default_products}
        industry_specific = [p for p in products if p["product_id"] not in default_ids]

        print(f"\n  {industry.upper()} Industry ({len(industry_specific)} unique products):")
        for product in industry_specific:
            pricing = (
                f"${product['cpm']} CPM"
                if product.get("cpm")
                else f"${product['price_guidance']['min']}-${product['price_guidance']['max']} CPM"
            )
            print(f"    • {product['name']}")
            print(f"      {product['description']}")
            print(f"      Pricing: {pricing}")

    # 3. API endpoints
    print("\n\n3. API Endpoints Available:")
    print("-" * 60)
    print("  GET  /api/tenant/<tenant_id>/products/suggestions")
    print("       Query params: industry, delivery_type, max_cpm, formats[]")
    print()
    print("  POST /api/tenant/<tenant_id>/products/quick-create")
    print('       Body: {"product_ids": ["run_of_site_display", "homepage_takeover"]}')
    print()
    print("  GET  /tenant/<tenant_id>/products/templates/browse")
    print("       Interactive template browser UI")
    print()
    print("  POST /tenant/<tenant_id>/products/bulk/upload")
    print("       Upload CSV/JSON with multiple products")

    # 4. AI Configuration
    print("\n\n4. AI Configuration Status:")
    print("-" * 60)

    if os.environ.get("GEMINI_API_KEY"):
        print("  ✅ GEMINI_API_KEY is configured")
        print("  ✅ Using Gemini 2.5 Flash for product configuration")
        print("  ✅ AI-assisted product creation is available")
    else:
        print("  ⚠️  GEMINI_API_KEY not set")
        print("  ⚠️  AI features will use default templates only")

    print("\n\n5. Usage Examples:")
    print("-" * 60)
    print("  # Create tenant with default products")
    print('  python scripts/setup/setup_tenant.py "My Publisher" --industry news')
    print()
    print("  # Test product suggestions API")
    print('  curl -H "x-adcp-auth: YOUR_TOKEN" \\')
    print('       "http://localhost:8080/api/tenant/TENANT_ID/products/suggestions?industry=sports"')
    print()
    print("  # Access Admin UI for visual management")
    print("  open http://localhost:8001")

    print("\n=== Demo Complete ===")


if __name__ == "__main__":
    demo_product_features()
