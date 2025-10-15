#!/usr/bin/env python3
"""
Audit and fix product pricing options in the database.

This script ensures every product has proper pricing_options set.
Products without pricing_options will be set to auction CPM with $1 floor.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select

from src.core.database.database_session import get_db_session
from src.core.database.models import Product, Tenant


def audit_products():
    """Audit all products and report on pricing status."""
    with get_db_session() as session:
        stmt = select(Product).join(Tenant)
        products = session.scalars(stmt).all()

        print("\n=== Product Pricing Audit ===")
        print(f"Total products: {len(products)}")

        needs_fix = []
        has_pricing = []

        for product in products:
            tenant_name = product.tenant.organization_name if product.tenant else "Unknown"

            # Check if product has pricing_options
            if product.pricing_options and len(product.pricing_options) > 0:
                has_pricing.append(product)
                print(f"✅ {product.product_id} ({tenant_name}): Has {len(product.pricing_options)} pricing option(s)")
            else:
                needs_fix.append(product)
                print(f"❌ {product.product_id} ({tenant_name}): NO pricing_options")
                # Also check legacy fields
                if hasattr(product, "is_fixed_price"):
                    print(f"   Legacy is_fixed_price: {product.is_fixed_price}")
                if hasattr(product, "pricing_model"):
                    print(f"   Legacy pricing_model: {product.pricing_model}")

        print("\n=== Summary ===")
        print(f"Products with pricing: {len(has_pricing)}")
        print(f"Products needing fix: {len(needs_fix)}")

        return needs_fix


def fix_products(products_to_fix, dry_run=True):
    """Fix products by adding default auction CPM pricing."""
    if not products_to_fix:
        print("\n✅ No products need fixing!")
        return

    print(f"\n=== Fixing {len(products_to_fix)} Products ===")
    mode = "DRY RUN" if dry_run else "APPLYING CHANGES"
    print(f"Mode: {mode}")

    # Default pricing option: Auction CPM with $1 floor
    default_pricing = {"pricing_model": "CPM", "pricing_type": "auction", "floor_price": 1.0, "currency": "USD"}

    with get_db_session() as session:
        for product in products_to_fix:
            # Re-fetch product in this session
            stmt = select(Product).where(Product.id == product.id)
            db_product = session.scalars(stmt).first()

            if not db_product:
                print(f"⚠️  Could not find product {product.product_id}")
                continue

            tenant_name = db_product.tenant.organization_name if db_product.tenant else "Unknown"

            print(f"\n📦 {db_product.product_id} ({tenant_name})")
            print(f"   Current pricing_options: {db_product.pricing_options}")
            print(f"   Setting to: {default_pricing}")

            if not dry_run:
                db_product.pricing_options = [default_pricing]
                session.add(db_product)

        if not dry_run:
            session.commit()
            print(f"\n✅ Fixed {len(products_to_fix)} products!")
        else:
            print("\n🔍 Dry run complete. Run with --apply to make changes.")


def main():
    """Main execution."""
    import argparse

    parser = argparse.ArgumentParser(description="Audit and fix product pricing")
    parser.add_argument("--apply", action="store_true", help="Apply fixes (default is dry run)")
    args = parser.parse_args()

    # Audit products
    products_to_fix = audit_products()

    # Fix products
    fix_products(products_to_fix, dry_run=not args.apply)


if __name__ == "__main__":
    main()
