#!/bin/bash
# Script to audit and fix product pricing in production via Fly.io SSH

set -e

echo "=== Product Pricing Audit & Fix Tool ==="
echo ""
echo "This script will:"
echo "1. Connect to the production database via Fly.io"
echo "2. Audit all products for missing pricing_options"
echo "3. Optionally fix products by setting auction CPM with \$1 floor"
echo ""

# Check if --apply flag is passed
APPLY_FLAG=""
if [[ "$1" == "--apply" ]]; then
    APPLY_FLAG="--apply"
    echo "⚠️  APPLY MODE: Changes will be committed to the database"
else
    echo "🔍 DRY RUN MODE: No changes will be made (use --apply to commit)"
fi

echo ""
read -p "Continue? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

echo ""
echo "Connecting to production..."

# Run the script via fly ssh console
fly ssh console --app adcp-sales-agent --command "python3 -c \"
import sys
from sqlalchemy import select
from src.core.database.database_session import get_db_session
from src.core.database.models import Product, Tenant

def audit_products():
    '''Audit all products and report on pricing status.'''
    with get_db_session() as session:
        stmt = select(Product).join(Tenant)
        products = session.scalars(stmt).all()

        print(f'\n=== Product Pricing Audit ===')
        print(f'Total products: {len(products)}')

        needs_fix = []
        has_pricing = []

        for product in products:
            tenant_name = product.tenant.organization_name if product.tenant else 'Unknown'

            # Check if product has pricing_options
            if product.pricing_options and len(product.pricing_options) > 0:
                has_pricing.append(product)
                print(f'✅ {product.product_id} ({tenant_name}): Has {len(product.pricing_options)} pricing option(s)')
            else:
                needs_fix.append(product)
                print(f'❌ {product.product_id} ({tenant_name}): NO pricing_options')

        print(f'\n=== Summary ===')
        print(f'Products with pricing: {len(has_pricing)}')
        print(f'Products needing fix: {len(needs_fix)}')

        return needs_fix

def fix_products(products_to_fix, apply_changes=False):
    '''Fix products by adding default auction CPM pricing.'''
    if not products_to_fix:
        print('\n✅ No products need fixing!')
        return

    print(f'\n=== Fixing {len(products_to_fix)} Products ===')
    mode = 'APPLYING CHANGES' if apply_changes else 'DRY RUN'
    print(f'Mode: {mode}')

    # Default pricing option: Auction CPM with \$1 floor
    default_pricing = {
        'pricing_model': 'CPM',
        'pricing_type': 'auction',
        'floor_price': 1.0,
        'currency': 'USD'
    }

    with get_db_session() as session:
        for product in products_to_fix:
            # Re-fetch product in this session
            stmt = select(Product).where(Product.id == product.id)
            db_product = session.scalars(stmt).first()

            if not db_product:
                print(f'⚠️  Could not find product {product.product_id}')
                continue

            tenant_name = db_product.tenant.organization_name if db_product.tenant else 'Unknown'

            print(f'\n📦 {db_product.product_id} ({tenant_name})')
            print(f'   Current pricing_options: {db_product.pricing_options}')
            print(f'   Setting to: {default_pricing}')

            if apply_changes:
                db_product.pricing_options = [default_pricing]
                session.add(db_product)

        if apply_changes:
            session.commit()
            print(f'\n✅ Fixed {len(products_to_fix)} products!')
        else:
            print(f'\n🔍 Dry run complete. Run with --apply to make changes.')

# Main execution
apply_mode = '$APPLY_FLAG' == '--apply'
products_to_fix = audit_products()
fix_products(products_to_fix, apply_changes=apply_mode)
\""

echo ""
echo "=== Done ==="
