#!/usr/bin/env python3
"""
Add pricing_options to ALL products that are missing them in production.

This script:
1. Finds all products without pricing_options
2. Adds default auction CPM pricing ($1 floor, $5 suggested) to each
3. Commits the changes
4. Reports results

Usage (in Fly.io SSH console):
    python scripts/maintenance/fix_all_missing_pricing_options.py

Or with custom pricing:
    python scripts/maintenance/fix_all_missing_pricing_options.py --floor 2.0 --suggested 10.0
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select

from src.core.database.database_session import get_db_session
from src.core.database.models import PricingOption, Product


def fix_all_missing_pricing_options(floor_price: float = 1.0, suggested_rate: float = 5.0, dry_run: bool = False):
    """
    Add pricing_options to all products that are missing them.

    Args:
        floor_price: Floor price for auction CPM pricing
        suggested_rate: Suggested rate for auction CPM pricing
        dry_run: If True, don't commit changes (just report what would be done)

    Returns:
        bool: True if all products now have pricing_options, False otherwise
    """

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

        print(f"\n{'='*80}")
        print("PRODUCTION PRICING OPTIONS FIX")
        print(f"{'='*80}\n")

        print(f"Total products in database: {len(products_by_id)}")
        print(f"Products WITH pricing_options: {len(products_by_id) - len(missing_pricing)}")
        print(f"Products MISSING pricing_options: {len(missing_pricing)}")

        if not missing_pricing:
            print("\n✅ ALL PRODUCTS ALREADY HAVE PRICING_OPTIONS - NO FIX NEEDED!\n")
            return True

        print(f"\n{'='*80}")
        print(f"{'DRY RUN - ' if dry_run else ''}ADDING PRICING_OPTIONS TO {len(missing_pricing)} PRODUCTS")
        print(f"{'='*80}\n")

        print("Default pricing configuration:")
        print("  - Pricing model: CPM (auction)")
        print("  - Currency: USD")
        print(f"  - Floor price: ${floor_price}")
        print(f"  - Suggested rate: ${suggested_rate}\n")

        fixed_count = 0
        for product in missing_pricing:
            print(f"{'[DRY RUN] ' if dry_run else ''}Adding pricing_options to: {product.product_id}")
            print(f"  Tenant: {product.tenant_id}")
            print(f"  Name: {product.name}")
            print(f"  Delivery Type: {product.delivery_type}")

            if not dry_run:
                pricing_option = PricingOption(
                    tenant_id=product.tenant_id,
                    product_id=product.product_id,
                    pricing_option_id="cpm_usd_auction",
                    pricing_model="cpm",
                    currency="USD",
                    is_fixed=False,
                    price_guidance={"floor": floor_price, "suggested_rate": suggested_rate},
                )
                session.add(pricing_option)
                fixed_count += 1

            print(
                f"  ✅ {'Would add' if dry_run else 'Added'} pricing_option: cpm_usd_auction (floor=${floor_price}, suggested=${suggested_rate})\n"
            )

        if not dry_run:
            session.commit()
            print(f"\n{'='*80}")
            print(f"✅ SUCCESS - FIXED {fixed_count} PRODUCTS")
            print(f"{'='*80}\n")
            print("All products now have pricing_options.")
            print("The migration can now proceed safely.")
        else:
            print(f"\n{'='*80}")
            print(f"DRY RUN COMPLETE - WOULD FIX {len(missing_pricing)} PRODUCTS")
            print(f"{'='*80}\n")
            print("Run without --dry-run to apply changes.")

        return True


def main():
    parser = argparse.ArgumentParser(description="Add pricing_options to all products missing them")
    parser.add_argument("--floor", type=float, default=1.0, help="Floor price for auction CPM (default: 1.0)")
    parser.add_argument("--suggested", type=float, default=5.0, help="Suggested rate for auction CPM (default: 5.0)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")

    args = parser.parse_args()

    try:
        success = fix_all_missing_pricing_options(
            floor_price=args.floor, suggested_rate=args.suggested, dry_run=args.dry_run
        )
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}\n", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
