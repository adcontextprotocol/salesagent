# Implementation Plan: Fix Pricing Migration & CI Infrastructure

## Problem Statement

The pricing model migration (commit 0c7a8ca4b, Oct 15 2025) changed Product pricing from direct fields to a separate PricingOption table. Out of 688 integration tests across 85 test files, approximately 514 tests are failing or skipped due to pricing migration issues.

**Root Causes:**
1. **Breaking Schema Change**: `Product(is_fixed_price=True, cpm=15.0)` → `PricingOption(pricing_model="CPM", rate=15.0, is_fixed=True)`
2. **Monolithic main.py**: 7924 lines makes refactoring risky and test fixes interdependent
3. **CI Partially Working**: 174 tests passing, 514 failing/skipped (CI uses `--ignore` to skip broken files)
4. **All-or-Nothing Problem**: Can't fix incrementally without infrastructure changes

## Architecture Decisions

### 1. Split Integration Tests into Two Suites

**Current State**: ~174 tests passing, ~514 failing/skipped in `tests/integration/`
- CI already uses `--ignore` to skip problematic test files
- Local `./run_all_tests.sh quick` works but skips many tests
- Some tests pass with pricing_options, others need migration

**Create `tests/integration_v2/` for cleaned tests:**
- Runs in CI as separate job (parallel to existing integration-tests)
- Only contains migrated/fixed tests
- Uses new pricing model patterns
- Tests run locally AND in CI from day 1

**Keep `tests/integration/` as-is:**
- Leave current CI configuration unchanged (keeps 174 tests passing)
- Move tests to integration_v2 as they're fixed
- CI continues running passing tests, skipping broken ones
- No functionality regression

### 2. Refactor main.py into Modules

**Problem:** 7924-line monolithic file
**Solution:** Extract into domain modules

```
src/core/
  ├── main.py              # MCP server setup + thin wrappers (500 lines)
  ├── operations/          # Business logic implementations
  │   ├── media_buy.py    # create_media_buy, update_media_buy
  │   ├── delivery.py     # get_media_buy_delivery
  │   ├── creatives.py    # sync_creatives, list_creatives
  │   ├── products.py     # get_products
  │   └── formats.py      # list_creative_formats, list_authorized_properties
  └── tools.py            # A2A raw functions (unchanged pattern)
```

**Benefits:**
- Easier to test individual operations
- Reduces merge conflicts
- Clearer ownership/responsibility
- Enables parallel work on different operations

### 3. CI Infrastructure Changes

**Add new GitHub Actions job (runs in parallel):**
```yaml
integration-tests-v2:
  name: Integration Tests V2 (Pricing Migration Fixed)
  runs-on: ubuntu-latest
  needs: [schema-sync]
  # PostgreSQL service (same as integration-tests)
  steps:
    - Run: pytest tests/integration_v2/ -v
```

**Keep existing integration-tests job unchanged:**
```yaml
integration-tests:
  name: Integration Tests (Legacy - 174 passing)
  # Keep current --ignore flags and markers
  # This continues to catch regressions in passing tests
  # As tests are fixed, they move to integration_v2
```

**Local test runner updates:**
- Update `./run_all_tests.sh` to run both suites
- Ensure integration_v2 tests work locally before CI

## Implementation Stages

### Stage 1: Infrastructure Setup
**Goal**: Create parallel test infrastructure without breaking existing tests
**Success Criteria**:
- integration_v2 job runs in CI (new, parallel job)
- Legacy integration tests continue running (174 passing tests unchanged)
- Local test runner (`./run_all_tests.sh`) runs both suites
- Zero regressions in existing passing tests

**Tasks:**
1. Create `tests/integration_v2/` directory with conftest.py
2. Add `integration-tests-v2` job to `.github/workflows/test.yml` (parallel to existing)
3. Keep `integration-tests` job running as-is (no changes)
4. Update `./run_all_tests.sh` to include integration_v2 tests
5. Create helper utilities for new pricing model in `tests/conftest_shared.py`
6. Verify local: `./run_all_tests.sh quick` passes
7. Verify CI: Both integration-tests and integration-tests-v2 pass

**Tests**:
- Local: `./run_all_tests.sh quick` passes (174 integration + 0 integration_v2)
- CI: Both jobs green (174 passing in old, 0 in new)

**Status**: ✅ Complete

---

### Stage 2: Extract Core Operations from main.py
**Goal**: Split main.py into manageable modules
**Success Criteria**:
- main.py < 1000 lines
- All MCP tools still work
- All A2A endpoints still work
- Unit tests pass

**Tasks:**
1. Create `src/core/operations/` directory structure
2. Extract `_create_media_buy_impl` → `operations/media_buy.py`
3. Extract `_get_media_buy_delivery_impl` → `operations/delivery.py`
4. Extract `_sync_creatives_impl` → `operations/creatives.py`
5. Extract `_get_products_impl` → `operations/products.py`
6. Update imports in main.py and tools.py
7. Verify MCP/A2A shared implementation pattern preserved

**Tests**:
- Unit tests pass
- Quick smoke test: `pytest tests/smoke/ -v`
- Import validation: `python -c "from src.core.main import mcp; from src.core.tools import create_media_buy_raw"`

**Status**: Not Started

---

### Stage 3: Create Pricing Test Fixtures
**Goal**: Standard helpers for creating products with pricing_options
**Success Criteria**:
- Simple API: `create_test_product_with_pricing(session, tenant_id, pricing_model="CPM", rate=15.0)`
- Covers all pricing models (CPM, VCPM, CPC, FLAT_RATE)
- Works in both integration and integration_v2 tests

**Tasks:**
1. Create `tests/conftest_shared.py` with pricing helpers:
   ```python
   def create_test_product_with_pricing(
       session,
       tenant_id: str,
       product_id: str = None,
       pricing_model: str = "CPM",
       rate: Decimal = Decimal("15.0"),
       is_fixed: bool = True,
       currency: str = "USD"
   ) -> Product
   ```
2. Add fixtures for common pricing scenarios
3. Document usage patterns in docstrings

**Tests**: Create sample product in integration_v2 test

**Status**: ✅ Complete (pricing helpers created)

---

### Stage 4: Migrate Critical Path Tests (Batch 1)
**Goal**: Fix ~10 most critical tests that validate core workflows
**Success Criteria**:
- Tests run green in integration_v2 locally AND in CI
- Cover: create_media_buy, get_products, sync_creatives
- Tests pass in isolation and with full suite

**Priority Tests** (from 26 files with legacy pricing):
1. test_mock_adapter.py (critical - used by many other tests)
2. test_create_media_buy_roundtrip.py (core workflow)
3. test_create_media_buy_v24.py (core workflow)
4. test_get_products_filters.py (product discovery)
5. test_product_creation.py (product management)
6. test_pricing_models_integration.py (pricing validation)
7. test_conftest.py (shared fixtures)

**Tasks for each test:**
1. Run locally first: `pytest tests/integration/test_X.py -v` (see current failures)
2. Copy to integration_v2/
3. Replace `Product(is_fixed_price=True, cpm=15.0)` → `create_test_product_with_pricing()`
4. Fix any other issues discovered
5. Test locally: `pytest tests/integration_v2/test_X.py -v` (must pass)
6. Test with suite: `./run_all_tests.sh quick` (must pass)
7. Commit individually with clear message
8. Verify in CI (integration-tests-v2 job)

**Tests**:
- Local isolated: Each test passes alone
- Local suite: `./run_all_tests.sh quick` passes
- CI: integration-tests-v2 job passes

**Status**: Not Started

---

### Stage 5: Migrate Admin UI Tests (Batch 2)
**Goal**: Fix ~8 admin UI tests with legacy pricing
**Success Criteria**:
- Admin product management tests pass locally and in CI
- Product edit/create/delete flows validated

**Admin Tests** (from 26 files with legacy pricing):
1. test_admin_ui_data_validation.py
2. test_admin_ui_pages.py
3. test_product_deletion.py
4. test_product_delete_with_pricing.py
5. test_product_formats_update.py
6. test_session_json_validation.py

**Tasks:**
1. Follow same process as Stage 4 for each test
2. Update admin UI test fixtures
3. Verify product edit/create/delete flows
4. Test locally before CI

**Tests**:
- Local: Each test passes, suite passes
- CI: integration-tests-v2 passes

**Status**: Not Started

---

### Stage 6: Migrate Remaining Integration Tests (Batch 3)
**Goal**: Fix remaining ~11 test files with legacy pricing
**Success Criteria**:
- All 26 files with legacy pricing migrated to integration_v2
- Both integration and integration_v2 suites pass locally and in CI

**Remaining Tests** (11 files):
1. test_mcp_tools_audit.py
2. test_get_products_format_id_filter.py (already ignored in CI)
3. test_a2a_error_responses.py (already ignored in CI)
4. test_minimum_spend_validation.py
5. test_media_buy_readiness.py
6. test_ai_products.py
7. test_generative_creatives.py
8. test_self_service_signup.py
9. test_template_url_validation.py
10. test_tenant_settings_comprehensive.py
11. Any other files discovered during Stages 4-5

**Tasks:**
1. Migrate remaining files following Stage 4 process
2. Run batch verification: `pytest tests/integration_v2/ -v` (locally first)
3. Verify both suites: `./run_all_tests.sh quick` passes
4. Update CI to remove `--ignore` flags (tests now in v2)
5. Keep both integration/ and integration_v2/ directories
   - integration/ has 174 passing tests (unchanged)
   - integration_v2/ has 26 migrated test files (all passing)

**Tests**:
- Local: Both suites pass
- CI: Both integration-tests and integration-tests-v2 pass

**Status**: Not Started

---

### Stage 7: Update Documentation
**Goal**: Document new patterns for future contributors
**Success Criteria**: Clear examples of pricing model usage

**Tasks:**
1. Update CLAUDE.md with pricing_options pattern
2. Add examples to test documentation
3. Create migration guide for remaining legacy code
4. Update ARCHITECTURE.md with new operations/ structure

**Tests**: Documentation review

**Status**: Not Started

---

## Success Metrics

**Current State**: 174 tests passing, 514 failing/skipped (688 total)
**Stage 1-3**: Infrastructure ready (174 tests still passing, 0 regressions)
**Stage 4**: ~10 critical tests passing in integration_v2 (locally + CI)
**Stage 5**: ~18 tests total in integration_v2 (10 + 8 admin tests)
**Stage 6**: All 26 files with legacy pricing migrated to integration_v2
**Stage 7**: Documentation complete

**Final State**:
- integration/: 174 tests passing (unchanged)
- integration_v2/: 26 migrated test files, all passing
- CI: Both suites green, no `--ignore` flags needed

## Risk Mitigation

**Risk**: Breaking existing functionality during refactor
**Mitigation**:
- Keep legacy integration tests intact (excluded from CI)
- Each migrated test committed individually
- Smoke tests run after each stage

**Risk**: Missing edge cases in pricing migration
**Mitigation**:
- Create comprehensive pricing fixtures covering all models
- Test both fixed and auction pricing
- Validate currency handling

**Risk**: main.py refactor breaks MCP/A2A
**Mitigation**:
- Preserve shared implementation pattern exactly
- Import validation checks after extraction
- Run quick MCP/A2A smoke tests

## Rollback Plan

If issues discovered:
1. Revert to current main branch
2. Integration_v2 is additive - can be removed safely
3. Main.py refactor can be reverted via git

## Timeline Estimate

- Stage 1: 1-2 hours (infrastructure + local testing)
- Stage 2: 2-3 hours (main.py refactor)
- Stage 3: 1 hour (pricing fixtures)
- Stage 4: 3-4 hours (~10 tests × 20min each, includes debugging)
- Stage 5: 2-3 hours (~8 tests × 20min each)
- Stage 6: 3-4 hours (~11 tests × 20min each)
- Stage 7: 1 hour (documentation)

**Total**: ~13-18 hours over 2-3 days

**Note**: Reduced from original estimate because:
- Only 26 test files need migration (not 91)
- 174 tests already passing (no migration needed)
- Parallel work possible (main.py refactor + test migration)

## Notes

- This plan allows incremental progress without blocking development
- CI will start passing again after Stage 4 (critical path tests)
- Legacy tests remain accessible for reference during migration
- main.py refactor (Stage 2) can proceed in parallel with test migration
