# AdCP v1 Schemas

This directory contains cached AdCP v1 schemas for offline validation.

- **Total Schemas**: 37 files (~160KB)
- **AdCP Version**: v2.4 (schemas v1)
- **Downloaded**: 2025-09-02
- **Source**: https://adcontextprotocol.org/

## Usage

```python
# Use v1 schemas (default)
async with AdCPSchemaValidator(adcp_version="v1") as validator:
    await validator.validate_response("get-products", data)
```

## Files

- `index.json` - Main schema registry
- `_schemas_v1_core_*.json` - Core data models (14 files)
- `_schemas_v1_enums_*.json` - Enumerations (6 files)
- `_schemas_v1_media-buy_*.json` - Media-buy tasks (12 files)
- `_schemas_v1_signals_*.json` - Signals tasks (4 files)

These schemas are checked into git for reliable CI validation.
