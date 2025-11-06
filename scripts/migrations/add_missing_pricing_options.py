#!/usr/bin/env python3
"""Add default pricing options to products that are missing them.

This script fixes products that were created without pricing_options,
which causes "Product has no pricing_options configured" errors.

Per AdCP spec, all products MUST have at least one pricing option.
"""

import sys
from decimal import Decimal
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import select

from src.core.database.database_session import get_db_session
from src.core.database.models import PricingOption, Product


def add_default_pricing_options():
    """Add default pricing options to products that don't have any."""
    print("🔧 Adding default pricing options to products...")

    with get_db_session() as session:
        # Find all products
        stmt = select(Product)
        products = session.scalars(stmt).all()

        print(f"Found {len(products)} total products")

        fixed_count = 0
        skipped_count = 0

        for product in products:
            # Check if product already has pricing options
            stmt_pricing = select(PricingOption).filter_by(tenant_id=product.tenant_id, product_id=product.product_id)
            existing_pricing = session.scalars(stmt_pricing).all()

            if len(existing_pricing) > 0:
                print(f"  ℹ️  {product.product_id}: Already has {len(existing_pricing)} pricing option(s)")
                skipped_count += 1
                continue

            # Product has no pricing options - add default
            print(f"  🔧 {product.product_id}: Adding default pricing option...")

            # Determine default pricing based on delivery_type
            if product.delivery_type == "guaranteed":
                # Guaranteed delivery: Use fixed CPM pricing
                pricing_option = PricingOption(
                    tenant_id=product.tenant_id,
                    product_id=product.product_id,
                    pricing_model="cpm",
                    rate=Decimal("15.00"),  # Default $15 CPM
                    currency="USD",
                    is_fixed=True,
                    price_guidance=None,
                    min_spend_per_package=None,
                    parameters=None,
                )
                print("     → CPM $15.00 (fixed, guaranteed delivery)")
            else:
                # Non-guaranteed delivery: Use auction CPM pricing with floor
                pricing_option = PricingOption(
                    tenant_id=product.tenant_id,
                    product_id=product.product_id,
                    pricing_model="cpm",
                    rate=None,  # No fixed rate for auction
                    currency="USD",
                    is_fixed=False,
                    price_guidance={"floor": 5.0, "p50": 10.0, "p90": 15.0},
                    min_spend_per_package=None,
                    parameters=None,
                )
                print("     → CPM auction (floor $5.00, non-guaranteed delivery)")

            session.add(pricing_option)
            fixed_count += 1

        # Commit all changes
        if fixed_count > 0:
            session.commit()
            print(f"\n✅ Added pricing options to {fixed_count} product(s)")
        else:
            print("\n✅ All products already have pricing options")

        print(f"   - Fixed: {fixed_count}")
        print(f"   - Skipped: {skipped_count}")
        print(f"   - Total: {len(products)}")

        # Verify all products now have pricing options
        print("\n🔍 Verification: Checking all products have pricing options...")
        stmt_check = select(Product)
        all_products = session.scalars(stmt_check).all()

        products_without_pricing = []
        for product in all_products:
            stmt_pricing = select(PricingOption).filter_by(tenant_id=product.tenant_id, product_id=product.product_id)
            pricing_count = len(session.scalars(stmt_pricing).all())

            if pricing_count == 0:
                products_without_pricing.append(product.product_id)

        if len(products_without_pricing) > 0:
            print(f"❌ ERROR: {len(products_without_pricing)} products still have no pricing options:")
            for prod_id in products_without_pricing:
                print(f"   - {prod_id}")
            return False
        else:
            print(f"✅ All {len(all_products)} products have pricing options")
            return True


if __name__ == "__main__":
    success = add_default_pricing_options()
    sys.exit(0 if success else 1)
