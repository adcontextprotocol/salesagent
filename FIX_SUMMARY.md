# Fix: Product Deletion with Pricing Options Constraint

## Problem
When trying to delete a product, the database trigger `prevent_empty_pricing_options` was blocking the deletion with this error:

```
Cannot delete last pricing option for product prod_3f24d945 (tenant tenant_wonderstruck).
Every product must have at least one pricing option.
```

## Root Cause
The PostgreSQL trigger was designed to prevent deletion of the last pricing option for a product (to maintain data integrity). However, when deleting a product itself, the cascade deletion of pricing_options would trigger this constraint check **before** the product was deleted, causing the product deletion to fail.

## Solution
Created migration `6ac7f95b69c6_fix_pricing_options_trigger_for_product_deletion.py` that updates the trigger to:

1. Check if the parent product still exists in the database
2. If the product doesn't exist (is being deleted), allow the cascade to proceed
3. Only enforce the constraint if the product exists and someone is trying to manually delete the last pricing option

## Updated Trigger Logic
```sql
-- Check if the parent product still exists
SELECT EXISTS(
    SELECT 1 FROM products
    WHERE tenant_id = OLD.tenant_id
      AND product_id = OLD.product_id
) INTO product_exists;

-- If product doesn't exist, it's being deleted - allow cascade
IF NOT product_exists THEN
    RETURN OLD;
END IF;

-- Product exists, check if this DELETE would leave it with no pricing options
-- (original constraint enforcement logic)
```

## To Apply
Run the migration:
```bash
# In production/staging with database running
uv run alembic upgrade head
```

## Testing
The migration includes both upgrade and downgrade paths. The fix maintains backward compatibility:
- Product deletion now works correctly
- Manual deletion of the last pricing option for an existing product is still blocked
- Data integrity constraint is preserved

## Related Files
- Migration: `alembic/versions/6ac7f95b69c6_fix_pricing_options_trigger_for_product_deletion.py`
- Product deletion code: `src/admin/blueprints/products.py:1009-1094` (delete_product function)
- Original trigger: `alembic/versions/b61ff75713c0_enforce_at_least_one_pricing_option_per_.py`
