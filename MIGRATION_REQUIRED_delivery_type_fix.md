# URGENT: Production Migration Required - delivery_type Validation Failure

## Issue Summary

**Status:** 🔴 BLOCKING PRODUCTION
**Date Discovered:** 2025-10-16
**Affected Systems:** All production sales agents (Wonderstruck, Test Agent, etc.)

### Problem

Production databases contain products with invalid `delivery_type` values:
- **Current (invalid):** `'non-guaranteed'` (hyphen)
- **Required (spec-compliant):** `'non_guaranteed'` (underscore)

This causes **all `get_products` calls to fail** with validation errors:

```
Product 'prod_e8fd6012' in database failed AdCP schema validation.
Error: 1 validation error for Product
delivery_type
  Input should be 'guaranteed' or 'non_guaranteed' [type=literal_error, input_value='non-guaranteed', input_type=str]
```

### Root Cause

1. **AdCP Spec** defines delivery_type enum as: `["guaranteed", "non_guaranteed"]` (underscore)
2. **Historic Data** used hyphenated format: `'non-guaranteed'`
3. **Schema Enforcement** now strictly validates per AdCP spec (src/core/schemas.py:654)
4. **Migration Exists** (`f9300bf2246d`) but **hasn't been run on production**

## Impact

- ❌ `get_products` fails for all agents
- ❌ Product discovery broken
- ❌ Cannot create new media buys (no products available)
- ❌ Wonderstruck integration test failing
- ❌ All AdCP workflows blocked

## Solution

### Migration Details

**File:** `alembic/versions/f9300bf2246d_fix_delivery_type_values_hyphen_to_.py`
**Revision:** `f9300bf2246d`
**Depends On:** `2453043b72da`
**Created:** 2025-10-16 10:00:09

**What it does:**
```sql
UPDATE products
SET delivery_type = 'non_guaranteed'
WHERE delivery_type = 'non-guaranteed'
```

### Deployment Steps

#### For Fly.io Production (Wonderstruck, Test Agent)

```bash
# 1. Check current migration state
fly ssh console --app wonderstruck-sales-agent
cd /app
uv run alembic current

# 2. Run pending migrations (includes f9300bf2246d)
uv run python migrate.py

# 3. Verify migration applied
uv run alembic current  # Should show f9300bf2246d or later

# 4. Verify data fixed
uv run python -c "
from src.core.database.database_session import get_db_session
from src.core.database.models import Product
from sqlalchemy import select

with get_db_session() as session:
    stmt = select(Product).where(Product.delivery_type == 'non-guaranteed')
    bad_products = session.scalars(stmt).all()
    print(f'Products with old format: {len(bad_products)}')

    stmt = select(Product).where(Product.delivery_type == 'non_guaranteed')
    good_products = session.scalars(stmt).all()
    print(f'Products with new format: {len(good_products)}')
"

# 5. Test get_products endpoint
curl -H "x-adcp-auth: <principal_token>" \
  https://wonderstruck.sales-agent.scope3.com/mcp/get_products
```

#### Repeat for Test Agent

```bash
fly ssh console --app test-agent
cd /app
uv run python migrate.py
# ... verify as above
```

### Verification

After migration:
- ✅ No products should have `delivery_type = 'non-guaranteed'`
- ✅ All products should have `delivery_type = 'guaranteed'` OR `'non_guaranteed'`
- ✅ `get_products` should return results without validation errors
- ✅ Run: `tsx scripts/manual-testing/full-wonderstruck-test.ts` should pass

## Prevention

1. **Schema Validation Tests:** `tests/unit/test_adcp_contract.py` enforces spec compliance
2. **Pre-commit Hooks:** Check for spec violations before commit
3. **Migration Testing:** Always test migrations locally before production
4. **CI/CD Integration:** Migrations run automatically on deploy

## References

- **AdCP Spec:** https://adcontextprotocol.org/schemas/v1/
- **Schema Definition:** `src/core/schemas.py:654`
- **Migration File:** `alembic/versions/f9300bf2246d_fix_delivery_type_values_hyphen_to_.py`
- **Related Issue:** Product validation blocking all workflows
- **Documentation:** `CLAUDE.md` sections on AdCP compliance and PostgreSQL-only architecture

## Next Steps

1. ✅ Document issue (this file)
2. ⏳ Deploy migration to Wonderstruck production
3. ⏳ Deploy migration to Test Agent production
4. ⏳ Verify all agents return products successfully
5. ⏳ Re-run Wonderstruck integration test
6. ⏳ Delete this file after successful deployment

---

**Created:** 2025-10-16
**Author:** Conductor Workspace (vatican-v3)
**Branch:** fix-delivery-type-validation
