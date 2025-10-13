# Pricing Fields Migration Plan

## Status: In Progress

This document tracks the migration from legacy product pricing fields to the new `pricing_options` table.

## Background

Products currently have pricing stored in two places:
- **Legacy fields**: `is_fixed_price`, `cpm`, `price_guidance`, `currency`, `delivery_type` (in `products` table)
- **New table**: `pricing_options` table with full support for multiple pricing models

This dual storage is dangerous and leads to inconsistencies (e.g., product list showing $65 when actual price is $3).

## Migration Strategy

### Phase 1: Data Migration ✅ READY TO DEPLOY
**Migration Created:**
- `5d949a78d36f_migrate_legacy_pricing_to_pricing_options.py` - Populates pricing_options from legacy fields
- **Note**: Legacy columns will NOT be dropped. Both storage methods remain active.

**Helper Function Created:**
- `src/core/database/product_pricing.py::get_product_pricing_options()` - Reads from either source

### Phase 2: Code Updates 🔄 IN PROGRESS (Post-Deploy)

**Critical Path (✅ DONE):**
- ✅ `product_catalog_providers/database.py` - Used by all MCP get_products calls
- ✅ `src/admin/blueprints/products.py` - Product list page
- ✅ `templates/products.html` - Product list template

**Remaining Files (📋 TODO):**
The following files still reference legacy pricing fields and need to be updated to use `get_product_pricing_options()`:

1. **Admin UI**:
   - `src/admin/blueprints/products.py` - edit_product() function (uses legacy fields for GAM form)
   - `templates/edit_product.html` - Edit product form
   - `templates/add_product_gam.html` - GAM product creation form
   - `src/admin/tests/conftest.py` - Test fixtures

2. **Core Logic**:
   - `src/core/main.py` - May have legacy field references
   - `src/services/dynamic_pricing_service.py` - Dynamic pricing calculations

3. **Other Catalog Providers**:
   - `product_catalog_providers/ai.py` - AI-powered product selection
   - `product_catalog_providers/signals.py` - Signals-based products

4. **Tests**:
   - `tests/unit/test_signals_discovery_provider.py`
   - `tests/unit/test_pricing_validation.py`
   - `tests/unit/test_auth_removal_simple.py`
   - `tests/unit/test_adcp_contract.py`
   - `tests/integration/test_product_creation.py`
   - `tests/integration/test_schema_database_mapping.py`
   - `tests/integration/test_mcp_tool_roundtrip_validation.py`
   - `tests/integration/test_main.py`
   - `tests/integration/test_get_products_database_integration.py`

5. **Tools & Examples**:
   - `tools/demos/demo_product_catalog_providers.py`
   - `examples/client_mcp.py`
   - `scripts/migrate_product_configs.py`

6. **Documentation**:
   - `docs/database-patterns.md` - Update examples

### Phase 3: Deploy and Run Migration ✅ READY

**Steps:**
1. Merge PR and deploy to production
2. Migration runs automatically: `5d949a78d36f` (populates pricing_options)
3. Verify all products have pricing_options (spot check)
4. Monitor for issues
5. **Legacy columns remain** - both storage methods active

### Phase 4: Update Remaining Code 📋 TODO (Future PR)

**Prerequisites:**
- Phase 3 complete and stable
- pricing_options working correctly in production

**Steps:**
1. Update remaining 21 files to use `get_product_pricing_options()`
2. Test thoroughly
3. Deploy and monitor

### Phase 5: Model Cleanup 🔒 FUTURE (Do NOT Do Yet)

**Prerequisites:**
- All code updated and tested in production
- Team decision to drop legacy columns
- Full database backup taken

**Steps:**
1. Create new migration to drop legacy columns
2. Update `src/core/database/models.py` - Remove legacy field definitions
3. Test all functionality
4. Optional: Remove fallback logic from helper

## Testing Checklist

Before running migrations:
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] Manual test: Create product with pricing_options
- [ ] Manual test: List products shows correct pricing
- [ ] Manual test: Edit product preserves pricing
- [ ] Manual test: MCP get_products returns correct pricing
- [ ] Manual test: Create media buy with product works

After first migration:
- [ ] Verify all existing products have pricing_options
- [ ] Verify pricing matches legacy fields
- [ ] Run full test suite

After second migration:
- [ ] Verify code still works
- [ ] No errors about missing columns
- [ ] All product operations work correctly

## Rollback Plan

### For This PR (Phase 3):
- If issues found, legacy fields still exist and work
- pricing_options can be safely ignored/deleted
- No data loss risk - legacy is still primary source for most code
- Can revert helper function changes if needed

### For Future Column Drops (Phase 5):
- ⚠️ **NOT included in this PR**
- Will require separate migration and PR
- Must have full backup before dropping columns
- Downgrade would restore empty columns (data lost)

## Progress Tracking

- **Migrations created**: 2025-01-13
- **Helper function created**: 2025-01-13
- **Critical path updated**: 2025-01-13
- **Remaining files**: 21
- **Files completed**: 3
- **Estimated remaining work**: 4-6 hours
