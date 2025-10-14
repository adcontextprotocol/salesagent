# Creative Formats Table Cleanup - URGENT

## Summary
The `creative_formats` table was **intentionally removed** in migration `f2addf453200` (Oct 13, 2025) because formats are now fetched from creative agents via AdCP. However, **significant code still references this table**, causing production failures.

## Production Status
- Migration: `953f2ffedf29` (includes table drop)
- Table exists: **NO** (dropped by design)
- Code still trying to use it: **YES** (multiple locations)

## Why Tests Didn't Catch This

### 1. Integration Tests Skipped in Quick Mode
```bash
# Quick mode (used during development)
pytest -m "not requires_db"  # Skips database-dependent tests

# CI mode (should catch it)
pytest  # Runs all tests including requires_db
```

### 2. Test Has Wrong Expectations
File: `tests/integration/test_tenant_settings_comprehensive.py`
Lines 65-82 explicitly query `creative_formats` table:
```python
cursor.execute("""
    SELECT format_id, name, width, height, 0 as auto_approve
    FROM creative_formats
    WHERE tenant_id = %s OR tenant_id IS NULL
""")
```

**This test EXPECTS the table to exist** even though it was dropped!

### 3. Local Dev DB May Have Stale Schema
If developers don't run migrations locally, their database may still have the old `creative_formats` table, hiding the issue.

## Code That Still References creative_formats

### Critical - Direct Database Access

1. **src/admin/blueprints/tenants.py** (FIXED in PR #401)
   - Line 237: Queries creative_formats table
   - **Status**: ✅ Fixed - now sets `creative_formats = []`

2. **src/admin/blueprints/creatives.py**
   - Entire blueprint for managing creative formats
   - Lines: 149, 322, 329, 412, 421, 465, 496, 544, 583
   - **Registered**: Yes (`app.register_blueprint(creatives_bp)`)
   - **Impact**: All `/tenant/{id}/creative-formats/*` routes will fail
   - **Status**: ❌ NEEDS FIX

3. **src/services/ai_creative_format_service.py**
   - Line 812: `select(CreativeFormat).filter_by(format_id=...)`
   - Line 817: Creates new CreativeFormat instances
   - **Status**: ❌ NEEDS FIX

4. **src/services/ai_product_service.py**
   - Line 380: `select(CreativeFormat)...`
   - **Status**: ❌ NEEDS FIX

### Model Still Exists

**src/core/database/models.py** - Lines 134-164
```python
class CreativeFormat(Base):
    __tablename__ = "creative_formats"  # ← Table doesn't exist!
    # ... full model definition
```

**Status**: ❌ Should be removed or marked deprecated

### Scripts That May Need Updates

1. `scripts/setup/populate_creative_formats.py` - Populates deleted table
2. `scripts/setup/populate_foundational_formats.py` - May reference table

## Remediation Options

### Option 1: Complete Removal (Recommended)
Remove all references to creative_formats since formats come from AdCP creative agents now.

**Steps:**
1. Remove `CreativeFormat` model from `src/core/database/models.py`
2. Remove `src/admin/blueprints/creatives.py` blueprint
3. Remove blueprint registration from `src/admin/app.py`
4. Update `src/services/ai_creative_format_service.py` to not use database
5. Update `src/services/ai_product_service.py` to not query creative_formats
6. Update test `tests/integration/test_tenant_settings_comprehensive.py` to not expect table
7. Remove or update population scripts
8. Add migration note to CHANGELOG

**Pros:**
- Clean break with legacy approach
- Aligns with AdCP v2.4 architecture
- Removes unused code

**Cons:**
- Requires careful refactoring of multiple files
- May impact features we're not aware of

### Option 2: Recreate Table (NOT Recommended)
Revert migration and keep the table.

**Pros:**
- Minimal code changes

**Cons:**
- Goes against architectural decision to fetch formats from creative agents
- Duplicates data that should come from AdCP
- Maintenance burden for legacy approach

## Immediate Action Required

### What's Already Fixed
- ✅ `src/admin/blueprints/tenants.py` settings page (PR #401)

### What Still Needs Fixing
1. **HIGH PRIORITY**: `src/admin/blueprints/creatives.py`
   - Remove blueprint OR
   - Refactor to use AdCP creative agent API instead of database

2. **HIGH PRIORITY**: Update tests
   - `tests/integration/test_tenant_settings_comprehensive.py` line 65-82
   - Remove expectation of creative_formats table

3. **MEDIUM PRIORITY**: Service layer
   - `src/services/ai_creative_format_service.py`
   - `src/services/ai_product_service.py`

4. **LOW PRIORITY**: Cleanup
   - Remove `CreativeFormat` model
   - Remove population scripts
   - Update documentation

## Next Steps

1. **Decision**: Choose Option 1 (Complete Removal) vs Option 2 (Recreate Table)
2. **Assess Impact**: Test all creative format related features
3. **Create Tasks**: Break down remediation into manageable PRs
4. **Update Tests**: Ensure all tests align with new architecture
5. **Document**: Update CLAUDE.md and architecture docs

## References

- Migration that dropped table: `alembic/versions/f2addf453200_add_agent_url_to_creatives_and_products.py`
- Migration comment (line 57): "Drop deprecated creative_formats table (no longer used)"
- Current production migration: `953f2ffedf29`
- PR fixing settings page: #401
