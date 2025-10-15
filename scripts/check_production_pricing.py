#!/usr/bin/env python3
"""
Check and fix product pricing in production.
Run this script on the production server via fly ssh console.

Usage:
    # Audit only (dry run):
    python scripts/check_production_pricing.py

    # Apply fixes:
    python scripts/check_production_pricing.py --apply
"""

import sys

from sqlalchemy import select

from src.core.database.database_session import get_db_session
from src.core.database.models import PricingOption, Product, Tenant


def main():
    apply_changes = "--apply" in sys.argv

    print("\n=== Product Pricing Audit ===")
    print(f"Mode: {'APPLY CHANGES' if apply_changes else 'DRY RUN'}\n")

    with get_db_session() as session:
        stmt = select(Product).join(Tenant)
        products = session.scalars(stmt).all()

        print(f"Total products: {len(products)}\n")

        needs_fix = []
        has_pricing = []

        for product in products:
            tenant_name = product.tenant.name if product.tenant else "Unknown"

            if product.pricing_options and len(product.pricing_options) > 0:
                has_pricing.append(product)
                print(f"✅ {product.product_id} ({tenant_name}): {len(product.pricing_options)} pricing option(s)")
            else:
                needs_fix.append(product)
                print(f"❌ {product.product_id} ({tenant_name}): NO pricing_options")

        print("\n=== Summary ===")
        print(f"Products with pricing: {len(has_pricing)}")
        print(f"Products needing fix: {len(needs_fix)}")

        if not needs_fix:
            print("\n✅ All products have pricing options!")
            return

        # Fix products by creating PricingOption records
        print(f"\n=== Fixing {len(needs_fix)} Products ===")

        for product in needs_fix:
            stmt = select(Product).where(Product.product_id == product.product_id)
            db_product = session.scalars(stmt).first()

            if not db_product:
                continue

            tenant_name = db_product.tenant.name if db_product.tenant else "Unknown"
            print(f"\n📦 {db_product.product_id} ({tenant_name})")
            print("   Adding auction CPM pricing option (floor: $1.00 USD)")

            if apply_changes:
                pricing_option = PricingOption(
                    tenant_id=db_product.tenant_id,
                    product_id=db_product.product_id,
                    pricing_model="CPM",
                    is_fixed=False,
                    price_guidance={"floor": 1.0},
                    currency="USD",
                )
                session.add(pricing_option)

        if apply_changes:
            session.commit()
            print(f"\n✅ Fixed {len(needs_fix)} products!")
        else:
            print("\n🔍 Dry run complete. Run with --apply to make changes.")


if __name__ == "__main__":
    main()
