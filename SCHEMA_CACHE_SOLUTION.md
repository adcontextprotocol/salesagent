# Schema Cache Solution

## Problem Summary

Our cached AdCP schemas were outdated and contained incorrect references to a non-existent `budget.json` schema. This caused our E2E tests to send wrong budget formats (objects instead of plain numbers).

## Root Cause

The schema validator (`tests/e2e/adcp_schema_validator.py`) downloads and caches schemas automatically during test runs, with a 24-hour validity period. However:

1. **No cleanup mechanism** - Old/incorrect schemas persisted in cache indefinitely
2. **Stale cache** - 78 cached files from earlier version of AdCP spec
3. **Budget.json reference** - Cached `package-request.json` referenced non-existent `budget.json`

## Solution Implemented

Created `scripts/refresh_adcp_schemas.py` that:

1. **Deletes all cached schemas** (clean slate)
2. **Downloads fresh schemas** from https://adcontextprotocol.org
3. **Verifies correctness** (checks for problematic files like `budget.json`)
4. **Reports results** (shows what was downloaded)

### Usage

```bash
# Dry run (see what would be deleted)
python scripts/refresh_adcp_schemas.py --dry-run

# Actual refresh
python scripts/refresh_adcp_schemas.py

# Specific version
python scripts/refresh_adcp_schemas.py --version v2
```

## Results

**Before refresh:**
- 78 cached schema files
- Included `_schemas_v1_core_budget_json.json` (incorrect)
- Package-request referenced non-existent `budget.json`

**After refresh:**
- 55 cached schema files (correct count)
- ✅ No `budget.json` references
- ✅ All budgets are plain `number` type per spec

## Verification

Confirmed budget format in official AdCP spec:

### Top-level budget (CreateMediaBuyRequest)
```json
"budget": {
  "type": "number",
  "description": "Total budget for this media buy. Currency is determined by the pricing_option_id selected in each package.",
  "minimum": 0
}
```

### Package-level budget (PackageRequest)
```json
"budget": {
  "type": "number",
  "description": "Budget allocation for this package in the media buy's currency",
  "minimum": 0
}
```

**Both are plain numbers!** No object with `{total, currency, pacing}` structure exists in the spec.

## Changes Made

### 1. Created Schema Refresh Script ✅
- `scripts/refresh_adcp_schemas.py`
- Cleans cache before downloading
- Verifies no outdated references remain

### 2. Fixed E2E Test Helper ✅
- `tests/e2e/adcp_request_builder.py`
- Line 76: Changed package budget from object to number
- Line 81: Changed top-level budget from object to number

### 3. Documented Findings ✅
- `BUDGET_FORMAT_FINDINGS.md` - Complete analysis
- `SCHEMA_CACHE_SOLUTION.md` - This document

## Process Going Forward

### When to Refresh Schemas

Run schema refresh when:
1. **AdCP spec updates** - New version released
2. **Test failures** - Validation errors suggest outdated schemas
3. **Schema inconsistencies** - Cached schemas don't match official spec
4. **Periodic maintenance** - Every few months to stay current

### Refresh Workflow

```bash
# 1. Backup current schemas (optional)
cp -r tests/e2e/schemas/v1 tests/e2e/schemas/v1.backup

# 2. Run refresh
python scripts/refresh_adcp_schemas.py

# 3. Verify tests pass
./run_all_tests.sh ci

# 4. Commit updated schemas
git add tests/e2e/schemas/v1/
git commit -m "chore: refresh AdCP schemas from official source"
```

### Preventing Stale Schemas

The schema validator has a 24-hour cache validity period (`_is_cache_valid()`). This is fine for local development, but we should:

1. **Run refresh before major releases** - Ensure prod uses latest schemas
2. **Document cache behavior** - Team knows schemas can be 24h old
3. **CI should use fresh schemas** - Consider clearing cache in CI runs

## Remaining TODOs

1. **Update Python schemas** - Make budget fields strictly `float` instead of `Budget | float`
2. **Remove Budget class** - If only used for AdCP fields (may be used internally elsewhere)
3. **Add pre-commit hook** - Run schema refresh if schemas are >30 days old
4. **CI integration** - Auto-refresh schemas weekly via scheduled job

## Key Learnings

1. **Cached data needs cleanup** - Without cleanup, stale data persists forever
2. **Verify against source** - Always check official spec when schemas seem wrong
3. **Trust but verify** - Test agent was correct; our cache was wrong
4. **Clean slate approach** - Delete all cached files before refresh ensures consistency

## Summary

The schema cache issue is now **RESOLVED**:
- ✅ Schemas refreshed from official source
- ✅ No `budget.json` references
- ✅ E2E test helper fixed
- ✅ Automated refresh script created
- ✅ Process documented

The test agent was correct all along - it properly implements the AdCP spec with plain number budgets. Our outdated cache caused the test failures.
