# Production Pricing Options Fix - Instructions

## Problem
Some products in production database are missing `pricing_options`, which blocks the pricing migration. Products like `native_lifestyle_feed` need pricing_options added before the migration can safely proceed.

## Solution
Run the fix script in Fly.io SSH console to add default pricing_options to ALL products missing them.

## Steps

### 1. SSH into Fly.io production
```bash
fly ssh console --app adcp-sales-agent
```

### 2. Navigate to app directory
```bash
cd /app
```

### 3. First, run audit to see what needs fixing (DRY RUN)
```bash
python scripts/maintenance/fix_all_missing_pricing_options.py --dry-run
```

This will show:
- How many products are missing pricing_options
- Which specific products need fixing
- What pricing will be added (default: CPM auction, $1 floor, $5 suggested)

### 4. Review the output and apply the fix
```bash
python scripts/maintenance/fix_all_missing_pricing_options.py
```

This will:
- Add `pricing_options` to every product that's missing them
- Use default auction CPM pricing (floor=$1, suggested=$5)
- Commit the changes to the database

### 5. Verify the fix worked
Run the audit script to confirm all products now have pricing_options:

```bash
python scripts/maintenance/audit_all_production_products.py
```

You should see:
```
✅ ALL PRODUCTS HAVE PRICING_OPTIONS - MIGRATION READY!
```

## What Gets Added

For each product missing pricing_options, the script adds:

```python
PricingOption(
    tenant_id=<product's tenant>,
    product_id=<product's id>,
    pricing_option_id='cpm_usd_auction',
    pricing_model='cpm',
    currency='USD',
    is_fixed=False,
    price_guidance={
        "floor": 1.0,          # $1 minimum CPM
        "suggested_rate": 5.0   # $5 suggested CPM
    }
)
```

## Custom Pricing (Optional)

If you want different default pricing:

```bash
# Higher pricing tiers
python scripts/maintenance/fix_all_missing_pricing_options.py --floor 2.0 --suggested 10.0

# Lower pricing tiers
python scripts/maintenance/fix_all_missing_pricing_options.py --floor 0.5 --suggested 3.0
```

## After Fix is Complete

Once all products have pricing_options:

1. ✅ Exit SSH console
2. ✅ The migration will now pass its safety check
3. ✅ Deploy the branch with the migration
4. ✅ Migration will drop legacy pricing columns safely

## Rollback (if needed)

If you need to undo the changes before committing:

```python
# In Python console (BEFORE running fix script)
from src.core.database.database_session import get_db_session
from src.core.database.models import PricingOption
from sqlalchemy import select, delete

with get_db_session() as session:
    # Delete all pricing_options added by this fix
    stmt = delete(PricingOption).where(
        PricingOption.pricing_option_id == 'cpm_usd_auction'
    )
    result = session.execute(stmt)
    session.commit()
    print(f"Deleted {result.rowcount} pricing_options")
```

## Timeline

**Current State:**
- ❌ Some products missing pricing_options (e.g., native_lifestyle_feed)
- ❌ Migration blocked by safety check
- ⚠️ Production API returning errors for products without pricing

**After Fix:**
- ✅ All products have pricing_options
- ✅ Migration safety check passes
- ✅ Production API works for all products
- ✅ Ready to deploy and run migration
