# Debugging Template Variable Errors: A Systematic Approach

## Problem Statement

The "Configuration" page was showing "Error loading settings" due to a systemic issue with SQLAlchemy/Pydantic model confusion. This document outlines the root cause, solution, and prevention strategy.

## Root Cause Analysis

### The Immediate Error
```
AttributeError: type object 'AdapterConfig' has no attribute 'model_validate_json'
```

**Cause**: Code was importing `AdapterConfig` from `models.py` (SQLAlchemy ORM) but trying to use `model_validate_json()` which is a Pydantic method.

### The Systemic Issue

The codebase underwent a **database schema migration** without updating all dependent code:

**Before (Legacy Schema):**
```sql
tenants (
  tenant_id TEXT,
  adapter_config TEXT  -- JSON string column
)
```

**After (Current Schema):**
```sql
tenants (tenant_id TEXT, ad_server TEXT)
adapter_config (tenant_id TEXT, adapter_type TEXT, gam_network_code TEXT, ...)
```

**Problem**: Code still expected `tenant.adapter_config` to be a JSON string, but it's now a **relationship** to the `AdapterConfig` table.

## Issues Found and Fixed

1. **tenants.py Line 166**: `AdapterConfig.model_validate_json(tenant.adapter_config)`
   - **Fix**: Access relationship fields directly: `tenant.adapter_config.adapter_type`

2. **tenants.py Lines 500, 542**: `json.loads(tenant.adapter_config)`
   - **Fix**: Direct field access instead of JSON parsing

3. **settings.py Line 190**: `json.loads(tenant.adapter_config)`
   - **Fix**: Rewrite function to work with new AdapterConfig table

4. **utils.py Line 58**: `parse_json_config(tenant.adapter_config)`
   - **Fix**: Build legacy JSON structure from relationship fields for backward compatibility

5. **gam_reporting_api.py Lines 334, 609**: `json.loads(adapter_config.config)`
   - **Fix**: Remove reference to non-existent `config` field

## Systematic Solution

### 1. Model Import Conventions

**File**: [`docs/model-import-conventions.md`](/Users/brianokelley/Developer/salesagent/.conductor/toronto/docs/model-import-conventions.md)

Clear guidelines for:
- When to import from `models.py` vs `schemas.py`
- Proper naming conventions for mixed imports
- Accessing relationships vs JSON fields

### 2. Validation Script

**File**: [`scripts/validate_model_confusion.py`](/Users/brianokelley/Developer/salesagent/.conductor/toronto/scripts/validate_model_confusion.py)

Automated detection of:
- Pydantic methods called on SQLAlchemy models
- `json.loads()` called on relationship fields
- Other common confusion patterns

**Usage**:
```bash
python3 scripts/validate_model_confusion.py
```

### 3. Backward Compatibility Layer

**File**: [`src/admin/utils.py`](/Users/brianokelley/Developer/salesagent/.conductor/toronto/src/admin/utils.py)

The `get_tenant_config_from_db()` function builds the legacy JSON structure from the new relational data, ensuring existing code continues to work.

## Prevention Strategy

### Pre-Commit Validation

Add to `.pre-commit-config.yaml`:
```yaml
- repo: local
  hooks:
    - id: model-confusion-check
      name: Check for SQLAlchemy/Pydantic model confusion
      entry: python3 scripts/validate_model_confusion.py
      language: system
      pass_filenames: false
```

### Code Review Checklist

When reviewing code changes:
- ✅ Are imports from the correct module (`models` vs `schemas`)?
- ✅ Are relationships accessed as objects, not JSON strings?
- ✅ Are Pydantic methods only called on Pydantic models?
- ✅ Is `json.loads()` only used on actual JSON strings?

### Developer Guidelines

1. **Read the schema**: Always check `\d table_name` before writing code
2. **Use the validator**: Run `python3 scripts/validate_model_confusion.py` before committing
3. **Follow conventions**: Use the import patterns in `docs/model-import-conventions.md`
4. **Test with real data**: Don't assume fields exist without verification

## Key Files Modified

| File | Change | Purpose |
|------|--------|---------|
| `src/admin/blueprints/tenants.py` | Fixed model confusion | Proper relationship access |
| `src/admin/blueprints/settings.py` | Rewrite adapter switching | Use new AdapterConfig table |
| `src/admin/utils.py` | Build legacy JSON from new schema | Backward compatibility |
| `adapters/gam_reporting_api.py` | Remove non-existent field access | Fix runtime errors |
| `scripts/validate_model_confusion.py` | NEW | Automated issue detection |
| `docs/model-import-conventions.md` | NEW | Developer guidelines |

## Testing the Fix

1. **Configuration Page**: Should load without "Error loading settings"
2. **Adapter Switching**: Should work through admin UI
3. **Template Rendering**: No more template variable errors
4. **Validation Script**: Should report "✅ No model confusion issues found!"

## Future Schema Changes

When making schema changes:
1. Update the schema migration guide
2. Run the validation script before and after changes
3. Update `get_tenant_config_from_db()` if needed for compatibility
4. Test all dependent UI pages

## Lessons Learned

1. **Schema migrations** require updating ALL dependent code, not just the database
2. **Relationships vs JSON fields** are fundamentally different and can't be used interchangeably
3. **Import statements** matter - always import from the correct module
4. **Automated validation** catches issues that manual review might miss
5. **Backward compatibility** can ease migration pain for complex schema changes
