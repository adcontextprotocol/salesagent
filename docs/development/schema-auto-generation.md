# AdCP Schema Management

## Overview

**As of adcp v1.2.1 migration, this project uses the official `adcp` Python library for all schema validation.**

The `adcp` library provides:
- ✅ Official Pydantic models from AdCP spec
- ✅ Automatic validation and type checking
- ✅ Always in sync with spec (library version = spec version)
- ✅ No local schema generation needed

## Migration from Local Schemas (Completed)

### What Changed

**Before (adcp v1.0.x)**:
- Locally generated Pydantic models in `src/core/schemas_generated/`
- Manual schema sync and generation scripts
- ~14,000 lines of generated code to maintain

**After (adcp v1.2.1)**:
- Import from `adcp.types.generated` package
- No local schema generation
- Library handles all validation

### New Usage Pattern

```python
# ✅ CORRECT - Import from adcp library
from adcp.types.generated import (
    CreateMediaBuyRequest,
    CreateMediaBuyResponse,
    GetProductsRequest,
    GetProductsResponse,
    Product,
)

# Use directly
request = CreateMediaBuyRequest(
    buyer_ref="example",
    packages=[...]
)
```

```python
# ❌ OLD PATTERN - No longer exists
from src.core.schemas_generated._schemas_v1_media_buy_create_media_buy_request_json import CreateMediaBuyRequest
```

## Custom Schema Helpers

For convenience, we provide helper functions in `src/core/schema_helpers.py`:

```python
from src.core.schema_helpers import create_get_products_request

# Helper validates and constructs request
req = create_get_products_request(
    brief="Display ads for e-commerce",
    brand_manifest={"name": "Acme Corp", "url": "https://acme.com"},
    filters={"formats": ["display_300x250"]}
)
```

Helpers provide:
- Cleaner API than direct Pydantic construction
- Domain-specific defaults
- Validation error handling
- Type hints for IDE support

## Cached Schema Files

The `schemas/v1/` directory contains cached JSON schemas used **only for E2E testing**:
- `tests/e2e/adcp_schema_validator.py` validates responses against official spec
- Schemas are auto-downloaded and cached
- NOT used for runtime validation (Pydantic models handle that)

**Purpose**: Verify our responses match the JSON Schema spec exactly (additional validation layer beyond Pydantic).

## When AdCP Spec Updates

### 1. Update adcp Library

```bash
# Update to new version
uv add adcp@latest

# Or specific version
uv add adcp@1.3.0
```

### 2. Update Code (if needed)

Check for breaking changes in the adcp library changelog:
- New required fields
- Renamed fields
- Changed types

### 3. Test Compatibility

```bash
# Run AdCP contract tests
pytest tests/unit/test_adcp_contract.py -v

# Run all tests
./run_all_tests.sh ci
```

## Benefits of Using Official Library

### ✅ Always In Sync
Library version directly corresponds to AdCP spec version. No drift possible.

### ✅ Reduced Maintenance
No schema generation scripts to maintain. Library updates = spec updates.

### ✅ Community Validation
Schemas are validated by the AdCP community and maintainers.

### ✅ Smaller Codebase
Removed ~14,000 lines of generated code from our repository.

### ✅ Better Type Safety
Library provides optimized Pydantic v2 models with full type hints.

## Custom Schemas

We still maintain custom Pydantic models in `src/core/schemas.py` for:
- Internal domain models (not in AdCP spec)
- Models with custom business logic
- Convenience wrappers around adcp models

Example:
```python
from src.core.schemas import AdCPBaseModel  # Custom base with environment-aware validation

class InternalModel(AdCPBaseModel):
    """Internal model not in AdCP spec."""
    # Custom fields and validators
```

## Troubleshooting

### Import Error from adcp.types.generated

**Problem**: `ImportError: cannot import name 'XYZ' from 'adcp.types.generated'`

**Solution**: Check adcp library version. The model may have been added in a newer version:
```bash
uv run python -c "import adcp; print(adcp.__version__)"
uv add adcp@latest
```

### Schema Version Mismatch

**Problem**: Response fails validation with "unexpected field" or "missing field"

**Solution**: Check if you're mixing adcp library versions. Ensure client and server use compatible versions:
```bash
# Check installed version
uv run pip show adcp

# Update to match client
uv add adcp@1.2.1
```

### Type Errors

**Problem**: Type checker complains about adcp models

**Solution**: The adcp library uses Pydantic v2. Ensure your type hints match:
```python
from adcp.types.generated import Product

# ✅ Correct
products: list[Product] = [...]

# ❌ Wrong
products: List[Product] = [...]  # Use list[], not List[]
```

## Removed Files (Post-Migration)

The following files/directories were removed in the adcp v1.2.1 migration:

- ❌ `src/core/schemas_generated/` (entire directory)
- ❌ `scripts/generate_schemas.py` (no longer needed)
- ❌ `.github/workflows/schema-sync.yml` (no longer needed)
- ❌ Pre-commit hook: `verify-schema-sync` (no longer needed)

## See Also

- AdCP Library: https://github.com/adcontextprotocol/adcp-python
- AdCP Spec: https://adcontextprotocol.org/docs/
- `tests/unit/test_adcp_contract.py` - Compliance tests
- `src/core/schema_helpers.py` - Helper functions
- `docs/testing/adcp-compliance.md` - Testing patterns
