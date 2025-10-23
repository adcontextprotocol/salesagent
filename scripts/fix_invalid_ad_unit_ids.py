#!/usr/bin/env python3
"""
Find and optionally fix products with invalid ad unit IDs.

This script:
1. Scans all products for GAM tenants
2. Identifies products with non-numeric ad unit IDs (codes/names instead of IDs)
3. Optionally fixes them by clearing invalid values (requires manual reconfiguration)

Usage:
    # Find problems (read-only)
    python scripts/fix_invalid_ad_unit_ids.py

    # Fix problems (clears invalid IDs - products need reconfiguration)
    python scripts/fix_invalid_ad_unit_ids.py --fix

    # Fix specific tenant
    python scripts/fix_invalid_ad_unit_ids.py --tenant tenant_wonderstruck --fix
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.orm import attributes

from src.core.database.database_session import get_db_session
from src.core.database.models import Product, Tenant


def is_valid_ad_unit_id(value):
    """Check if a value is a valid numeric ad unit ID."""
    return str(value).strip().isdigit()


def find_invalid_products(tenant_id=None):
    """Find all products with invalid ad unit IDs.

    Returns:
        List of (product, invalid_ids) tuples
    """
    invalid_products = []

    with get_db_session() as session:
        # Get GAM tenants
        stmt = select(Tenant)
        if tenant_id:
            stmt = stmt.where(Tenant.tenant_id == tenant_id)
        else:
            stmt = stmt.where(Tenant.ad_server == "google_ad_manager")

        tenants = session.scalars(stmt).all()

        if not tenants:
            print("No GAM tenants found")
            return []

        print(f"Checking {len(tenants)} GAM tenant(s)...")

        for tenant in tenants:
            print(f"\nTenant: {tenant.name} ({tenant.tenant_id})")

            # Get all products for this tenant
            stmt = select(Product).where(Product.tenant_id == tenant.tenant_id)
            products = session.scalars(stmt).all()

            print(f"  Found {len(products)} products")

            for product in products:
                impl_config = product.implementation_config or {}
                ad_unit_ids = impl_config.get("targeted_ad_unit_ids", [])

                if not ad_unit_ids:
                    continue

                # Check for invalid IDs
                invalid_ids = [id for id in ad_unit_ids if not is_valid_ad_unit_id(id)]

                if invalid_ids:
                    invalid_products.append((product, invalid_ids))
                    print(f"  ❌ {product.name} ({product.product_id})")
                    print(f"     Invalid IDs: {invalid_ids}")
                    print(f"     All IDs: {ad_unit_ids}")

    return invalid_products


def fix_invalid_products(invalid_products, dry_run=True):
    """Fix products by removing invalid ad unit IDs.

    Args:
        invalid_products: List of (product, invalid_ids) tuples
        dry_run: If True, don't actually save changes
    """
    if not invalid_products:
        print("\n✅ No invalid products found!")
        return

    print(f"\n{'DRY RUN - ' if dry_run else ''}Fixing {len(invalid_products)} products...")

    with get_db_session() as session:
        for product, invalid_ids in invalid_products:
            impl_config = product.implementation_config or {}
            ad_unit_ids = impl_config.get("targeted_ad_unit_ids", [])

            # Filter out invalid IDs, keeping only valid numeric ones
            valid_ids = [id for id in ad_unit_ids if is_valid_ad_unit_id(id)]

            print(f"\n  Product: {product.name} ({product.product_id})")
            print(f"    Before: {ad_unit_ids}")
            print(f"    After:  {valid_ids}")
            print(f"    Removed: {invalid_ids}")

            if not dry_run:
                # Refresh the product from this session
                stmt = select(Product).where(Product.product_id == product.product_id)
                product = session.scalars(stmt).first()

                if product:
                    impl_config = product.implementation_config or {}

                    if valid_ids:
                        impl_config["targeted_ad_unit_ids"] = valid_ids
                    else:
                        # Remove the key entirely if no valid IDs remain
                        impl_config.pop("targeted_ad_unit_ids", None)

                    product.implementation_config = impl_config
                    attributes.flag_modified(product, "implementation_config")
                    session.commit()
                    print("    ✅ Fixed!")

                    if not valid_ids:
                        print("    ⚠️  WARNING: No valid ad unit IDs remain. Product needs inventory reconfiguration.")

    if dry_run:
        print("\n⚠️  DRY RUN - No changes were saved. Use --fix to apply changes.")
    else:
        print("\n✅ All invalid products have been fixed!")
        print("\n⚠️  NOTE: Products with no valid IDs remaining need inventory reconfiguration via Admin UI.")


def main():
    parser = argparse.ArgumentParser(description="Find and fix products with invalid ad unit IDs")
    parser.add_argument("--tenant", help="Specific tenant ID to check (default: all GAM tenants)")
    parser.add_argument("--fix", action="store_true", help="Actually fix the problems (default: dry-run)")
    args = parser.parse_args()

    print("=" * 80)
    print("Finding products with invalid ad unit IDs...")
    print("=" * 80)

    invalid_products = find_invalid_products(args.tenant)

    if invalid_products:
        print(f"\n{'!' * 80}")
        print(f"Found {len(invalid_products)} products with invalid ad unit IDs")
        print(f"{'!' * 80}")

        if args.fix:
            print("\n⚠️  Proceeding with fixes...")
            fix_invalid_products(invalid_products, dry_run=False)
        else:
            print("\n💡 Run with --fix to remove invalid IDs (products will need reconfiguration)")
            fix_invalid_products(invalid_products, dry_run=True)
    else:
        print("\n✅ All products have valid ad unit IDs!")

    return 0 if not invalid_products else 1


if __name__ == "__main__":
    sys.exit(main())
