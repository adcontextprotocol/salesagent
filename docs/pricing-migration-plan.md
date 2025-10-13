# Pricing Fields Migration Plan

## Status: In Progress

This document tracks the migration from legacy product pricing fields to the new `pricing_options` table.

## Background

Products currently have pricing stored in two places:
- **Legacy fields**: `is_fixed_price`, `cpm`, `price_guidance`, `currency`, `delivery_type` (in `products` table)
- **New table**: `pricing_options` table with full support for multiple pricing models

This dual storage is dangerous and leads to inconsistencies (e.g., product list showing $65 when actual price is $3).

## Migration Strategy

### Phase 1: Data Migration ✅ READY
**Migrations Created:**
- `5d949a78d36f_migrate_legacy_pricing_to_pricing_options.py` - Populates pricing_options from legacy fields
- `56781b48ed8a_remove_legacy_pricing_fields.py` - Drops legacy columns

**Helper Function Created:**
- `src/core/database/product_pricing.py::get_product_pricing_options()` - Reads from either source

### Phase 2: Code Updates 🔄 IN PROGRESS

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

### Phase 3: Run Migrations 🔒 BLOCKED

**Prerequisites:**
- All code must be updated to use `get_product_pricing_options()`
- All tests must pass
- Code review complete

**Steps:**
1. Deploy code changes to production (code works with both storage methods)
2. Run first migration: `alembic upgrade 5d949a78d36f` (populates pricing_options)
3. Verify all products have pricing_options (spot check)
4. Monitor for 24 hours
5. Run second migration: `alembic upgrade head` (drops legacy columns)

### Phase 4: Model Cleanup 🔒 BLOCKED

**Prerequisites:**
- Both migrations have run successfully
- Legacy columns no longer exist in database

**Steps:**
1. Update `src/core/database/models.py` - Remove legacy field definitions:
   - Remove: `is_fixed_price`, `cpm`, `price_guidance`, `currency`, `delivery_type`
   - Keep: `pricing_options` relationship
2. Test all functionality
3. Remove `get_product_pricing_options()` fallback logic (optional - can keep for safety)

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

### If issues found before second migration:
- Keep using legacy fields
- pricing_options can be safely deleted (not used as primary source yet)

### If issues found after second migration:
- Run downgrade: `alembic downgrade 5d949a78d36f`
- This restores empty columns (data lost!)
- Must restore from backup if needed

**Important:** Once legacy columns are dropped, downgrade does NOT restore data. Make backups!

## Progress Tracking

- **Migrations created**: 2025-01-13
- **Helper function created**: 2025-01-13
- **Critical path updated**: 2025-01-13
- **Remaining files**: 21
- **Files completed**: 3
- **Estimated remaining work**: 4-6 hours
