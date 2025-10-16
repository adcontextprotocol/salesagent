# Fix Invalid Ad Unit IDs

## Problem

Some products may have been saved with ad unit **codes** or **names** (like `ca-pub-7492322059512158` or `Top banner`) instead of numeric **IDs** (like `23312403859`) that GAM requires.

This causes media buy creation to fail with:
```
RequiredError.REQUIRED @ lineItem[0].targeting.inventoryTargeting
```

## Solution

Use the `fix_invalid_ad_unit_ids.py` script to find and fix these products.

## Usage

### 1. Find Problems (Read-Only)

Check what needs to be fixed without making changes:

```bash
# Via Fly.io SSH
fly ssh console -a adcp-sales-agent
cd /app
python scripts/fix_invalid_ad_unit_ids.py
```

This will show:
- All GAM tenants
- Products with invalid ad unit IDs
- What the invalid values are

### 2. Fix Problems

Remove invalid IDs (products will need reconfiguration via Admin UI):

```bash
# Fix all GAM tenants
python scripts/fix_invalid_ad_unit_ids.py --fix

# Fix specific tenant only
python scripts/fix_invalid_ad_unit_ids.py --tenant tenant_wonderstruck --fix
```

### 3. Reconfigure Products

After running with `--fix`, products with no valid IDs remaining will need inventory reconfiguration:

1. Go to Admin UI → Products
2. Click "Edit" on the affected product
3. Click "Browse Ad Units"
4. Select the correct ad units from the inventory tree
5. Save the product

The UI will automatically save numeric IDs (not codes/names).

## What It Does

**Find mode (no --fix):**
- Scans all GAM tenant products
- Reports products with non-numeric ad unit IDs
- Shows what values are invalid
- Safe - makes no changes

**Fix mode (--fix):**
- Removes invalid (non-numeric) ad unit IDs
- Keeps valid numeric IDs if any exist
- Marks products needing reconfiguration
- Updates database with corrected values

## Example Output

```
================================================================================
Finding products with invalid ad unit IDs...
================================================================================
Checking 1 GAM tenant(s)...

Tenant: Wonderstruck (tenant_wonderstruck)
  Found 3 products
  ❌ Display Banner Network (prod_abc123)
     Invalid IDs: ['ca-pub-7492322059512158', 'Top banner']
     All IDs: ['ca-pub-7492322059512158', 'Top banner', '23312403859']

!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
Found 1 products with invalid ad unit IDs
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

💡 Run with --fix to remove invalid IDs (products will need reconfiguration)

DRY RUN - Fixing 1 products...

  Product: Display Banner Network (prod_abc123)
    Before: ['ca-pub-7492322059512158', 'Top banner', '23312403859']
    After:  ['23312403859']
    Removed: ['ca-pub-7492322059512158', 'Top banner']

⚠️  DRY RUN - No changes were saved. Use --fix to apply changes.
```

## Prevention

The GAM adapter now validates ad unit IDs and will reject non-numeric values with a clear error message. This prevents the problem from happening again.

To ensure products are created correctly:
1. Always use "Browse Ad Units" button in product form
2. Don't manually type ad unit codes or names
3. Let the UI select from the inventory tree
