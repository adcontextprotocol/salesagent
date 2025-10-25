# AdCP v1 Schemas

This directory contains cached AdCP v1 schemas for offline validation.

- **Total Schemas**: 86 files + 85 metadata files (~160KB)
- **AdCP Version**: v2.4 (schemas v1)
- **Source**: https://adcontextprotocol.org/schemas/v1/
- **Auto-Updated**: Yes, during workspace startup

## Automatic Schema Management

Schemas are **automatically downloaded/refreshed** when you open a workspace:

1. **Workspace Startup**: `scripts/setup/setup_conductor_workspace.sh` runs `refresh_adcp_schemas.py`
2. **ETag-Based Caching**: Only downloads if schemas have changed on server (HTTP 304 check)
3. **Fallback to Cache**: Uses cached schemas if download fails (offline mode)
4. **Git Committed**: Schemas are checked into git for reliable CI/offline usage

## Manual Schema Management

```bash
# Download latest schemas from official registry
uv run python scripts/refresh_adcp_schemas.py

# Dry-run to see what would change
uv run python scripts/refresh_adcp_schemas.py --dry-run

# Use offline mode (no downloads)
OFFLINE_MODE=1 pytest tests/e2e/
```

## Usage in Tests

```python
# Use v1 schemas (default)
async with AdCPSchemaValidator(adcp_version="v1") as validator:
    await validator.validate_response("get-products", data)

# Offline mode (use cache only)
async with AdCPSchemaValidator(offline_mode=True) as validator:
    await validator.validate_response("get-products", data)
```

## Files

- `index.json` - Main schema registry
- `_schemas_v1_core_*.json` - Core data models (24+ files)
- `_schemas_v1_enums_*.json` - Enumerations (11+ files)
- `_schemas_v1_media-buy_*.json` - Media-buy tasks (12+ files)
- `_schemas_v1_signals_*.json` - Signals tasks (4+ files)
- `_schemas_v1_pricing-options_*.json` - Pricing options (8+ files)
- `*.json.meta` - Cache metadata (ETag, Last-Modified)

## Why Schemas Are Always Available

1. **Checked into Git**: Schemas are committed, so fresh clones have them
2. **Workspace Startup**: Automatically refreshed when workspace opens
3. **ETag Caching**: Uses HTTP conditional requests to avoid unnecessary downloads
4. **Offline Fallback**: Works without network if schemas are cached

If schemas appear to "disappear", it's likely due to:
- Git operations (checkout, reset) affecting `schemas/v1/` directory
- Manual deletion of `schemas/v1/` directory
- File system issues

**Solution**: Run `uv run python scripts/refresh_adcp_schemas.py` to re-download all schemas.
