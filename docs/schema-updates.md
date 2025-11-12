# AdCP Schema Management (Updated for adcp v1.2.1)

## Overview

**As of adcp v1.2.1 migration, this project uses the official `adcp` Python library for schema validation.**

The local `schemas/v1/` directory is now **only used for E2E testing** - NOT for runtime validation.

## What Changed

### Before (adcp v1.0.x)
- Locally cached schemas in `schemas/v1/` used for Pydantic generation
- Manual schema sync and validation
- Pre-commit hooks to keep schemas in sync
- ~14,000 lines of generated Pydantic code

### After (adcp v1.2.1)
- Import Pydantic models from `adcp.types.generated` package
- Cached schemas ONLY used by E2E test validator (`tests/e2e/adcp_schema_validator.py`)
- No schema generation needed
- Library updates = spec updates

## Cached Schemas Purpose

The `schemas/v1/` directory now serves a single purpose:

**E2E JSON Schema Validation**: Verify our responses match the JSON Schema spec exactly (additional validation layer beyond Pydantic).

Files:
- Auto-downloaded by `tests/e2e/adcp_schema_validator.py`
- Cached locally for offline testing
- NOT used for runtime validation

## When AdCP Spec Updates

### 1. Update adcp Library

```bash
# Update to new version
uv add adcp@latest

# Or specific version
uv add adcp@1.3.0
```

### 2. Clear Cached Test Schemas (Optional)

```bash
# Remove cached E2E test schemas to force re-download
rm -rf schemas/v1/*.json schemas/v1/*.meta

# Next E2E test run will download latest schemas
pytest tests/e2e/test_adcp_compliance.py
```

### 3. Test Compatibility

```bash
# Run AdCP contract tests
pytest tests/unit/test_adcp_contract.py -v

# Run E2E validation
pytest tests/e2e/test_adcp_compliance.py -v

# Run all tests
./run_all_tests.sh ci
```

## Removed Features

The following schema management features were removed in the adcp v1.2.1 migration:

- ❌ `scripts/generate_schemas.py` - No longer needed (use adcp library)
- ❌ `scripts/check_schema_sync.py` - No longer needed (library is source of truth)
- ❌ Pre-commit hook: `verify-schema-sync` - No longer needed
- ❌ CI workflow: `schema-sync.yml` - No longer needed
- ❌ `src/core/schemas_generated/` - Removed (use `from adcp.types.generated`)

## Troubleshooting

### E2E Tests Fail with Schema Validation Errors

**Problem**: E2E tests fail with "schema validation failed" errors

**Solution**:
1. Check if cached schemas are outdated:
   ```bash
   # Clear cache and re-download
   rm -rf schemas/v1/*.json schemas/v1/*.meta
   pytest tests/e2e/test_adcp_compliance.py
   ```

2. Check if adcp library version matches:
   ```bash
   uv run python -c "import adcp; print(adcp.__version__)"
   ```

### Response Doesn't Match Pydantic Model

**Problem**: Runtime validation passes but E2E JSON schema validation fails

**Solution**: This indicates a discrepancy between Pydantic models and JSON Schema. Report to adcp library maintainers:
```bash
# Gather information
uv run python -c "import adcp; print(f'adcp version: {adcp.__version__}')"
pytest tests/e2e/test_adcp_compliance.py -v --tb=short
```

### Import Error from adcp.types.generated

**Problem**: `ImportError: cannot import name 'XYZ' from 'adcp.types.generated'`

**Solution**: Update adcp library to get newer models:
```bash
uv add adcp@latest
```

## Schema Files We Keep

### Keep: schemas/v1/*.json (Test Schemas)
- Used by E2E test validator only
- Auto-downloaded and cached
- Can be deleted and regenerated anytime

### Removed: src/core/schemas_generated/ (Generated Code)
- Replaced by `adcp.types.generated`
- No longer needed

### Keep: src/core/schemas.py (Custom Models)
- Internal domain models
- Custom business logic
- Convenience wrappers

## See Also

- AdCP Library: https://github.com/adcontextprotocol/adcp-python
- `docs/development/schema-auto-generation.md` - Detailed migration guide
- `tests/e2e/adcp_schema_validator.py` - E2E validator implementation
- `tests/unit/test_adcp_contract.py` - Pydantic compliance tests
