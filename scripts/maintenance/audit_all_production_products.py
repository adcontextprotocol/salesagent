#!/usr/bin/env python3
"""
Audit ALL products in production to find any missing pricing_options.

Usage:
    python scripts/maintenance/audit_all_production_products.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select

from src.core.database.database_session import get_db_session
from src.core.database.models import PricingOption, Product


def audit_all_products():
    """Find ALL products missing pricing_options in production database."""

    with get_db_session() as session:
        # Get all products with their pricing_options
        stmt = select(Product, PricingOption).outerjoin(
            PricingOption,
            (Product.tenant_id == PricingOption.tenant_id) & (Product.product_id == PricingOption.product_id),
        )
        results = session.execute(stmt).all()

        # Group by product
        products_by_id = {}
        for product, pricing_option in results:
            key = (product.tenant_id, product.product_id)
            if key not in products_by_id:
                products_by_id[key] = {"product": product, "pricing_options": []}
            if pricing_option:
                products_by_id[key]["pricing_options"].append(pricing_option)

        # Find products without pricing_options
        missing_pricing = []
        for (_tenant_id, _product_id), data in products_by_id.items():
            if not data["pricing_options"]:
                missing_pricing.append(data["product"])

        print(f"\n{'=' * 80}")
        print("PRODUCTION PRODUCT PRICING AUDIT")
        print(f"{'=' * 80}\n")

        print(f"Total products in database: {len(products_by_id)}")
        print(f"Products WITH pricing_options: {len(products_by_id) - len(missing_pricing)}")
        print(f"Products MISSING pricing_options: {len(missing_pricing)}")

        if missing_pricing:
            print(f"\n{'=' * 80}")
            print("⚠️  PRODUCTS MISSING PRICING_OPTIONS (BLOCKING MIGRATION)")
            print(f"{'=' * 80}\n")

            for product in missing_pricing:
                print(f"❌ {product.product_id}")
                print(f"   Tenant: {product.tenant_id}")
                print(f"   Name: {product.name}")
                print(f"   Delivery Type: {product.delivery_type}")
                print()

            print(f"{'=' * 80}")
            print("⚠️  ACTION REQUIRED")
            print(f"{'=' * 80}\n")
            print("These products MUST have pricing_options added before migration can proceed.")
            print("\nRecommended fix (run in Fly.io SSH console):")
            print("\n```python")
            print("from src.core.database.database_session import get_db_session")
            print("from src.core.database.models import PricingOption")
            print("from sqlalchemy import select")
            print()
            print("with get_db_session() as session:")

            for product in missing_pricing:
                print(f"    # Fix {product.product_id}")
                print("    session.add(PricingOption(")
                print(f"        tenant_id='{product.tenant_id}',")
                print(f"        product_id='{product.product_id}',")
                print("        pricing_option_id='cpm_usd_auction',")
                print("        pricing_model='cpm',")
                print("        currency='USD',")
                print("        is_fixed=False,")
                print('        price_guidance={"floor": 1.0, "suggested_rate": 5.0}')
                print("    ))")
                print()

            print("    session.commit()")
            print("```")

            return False
        else:
            print("\n✅ ALL PRODUCTS HAVE PRICING_OPTIONS - MIGRATION READY!\n")
            return True


if __name__ == "__main__":
    success = audit_all_products()
    sys.exit(0 if success else 1)
