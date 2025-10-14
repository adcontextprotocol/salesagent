# AdCP v2.4 Format ID Object Support

## Summary

The agent now supports the AdCP v2.4 `format_id` object structure alongside the legacy string format, providing full backward compatibility.

## Changes Made

### 1. New FormatId Pydantic Model

Added `FormatId` model in `src/core/schemas.py`:
```python
class FormatId(BaseModel):
    """AdCP v2.4 format identifier object."""
    agent_url: str = Field(..., description="URL of the agent defining this format")
    id: str = Field(..., pattern=r"^[a-zA-Z0-9_-]+$", description="Format identifier")
    model_config = {"extra": "forbid"}
```

Per AdCP spec at https://adcontextprotocol.org/schemas/v1/core/format-id.json

### 2. Updated Creative Model

Modified `Creative.format` field to accept both string and FormatId object:
```python
format: str | FormatId = Field(
    alias="format_id",
    description="Creative format type per AdCP spec (string for legacy, object for v2.4+)"
)
```

Added helper methods:
- `get_format_string()` - Returns format ID as string regardless of input type
- `get_format_agent_url()` - Returns agent URL if FormatId object, None if string

### 3. Format Normalization Helper

Added `_normalize_format_value()` in `src/core/main.py`:
```python
def _normalize_format_value(format_value: Any) -> str:
    """Normalize format value from either string or FormatId object to string."""
```

This handles:
- Legacy string format: `"display_300x250"`
- New dict format from wire: `{"agent_url": "...", "id": "display_300x250"}`
- FormatId object: `FormatId(agent_url="...", id="display_300x250")`

### 4. Updated Code Paths

Updated all code that accesses `creative.format` to use helper methods:
- `_convert_creative_to_adapter_asset()` - Uses `get_format_string()`
- `sync_creatives` implementation - Uses `_normalize_format_value()` for dict inputs

## Database Storage

The database `creatives.format` column remains a `VARCHAR(100)` storing only the format ID string (e.g., "display_300x250"). When receiving FormatId objects, we extract the `id` field for storage.

The `agent_url` is not stored in the database currently, as it's primarily for format discovery and validation at the API layer.

## Backward Compatibility

✅ **Legacy string format still works**:
```json
{
  "creative_id": "c1",
  "format_id": "display_300x250"
}
```

✅ **New object format now works**:
```json
{
  "creative_id": "c1",
  "format_id": {
    "agent_url": "https://creative.adcontextprotocol.org",
    "id": "display_300x250"
  }
}
```

## Testing

Added comprehensive tests in `tests/unit/test_format_id.py`:
- FormatId model validation
- Creative accepts both string and object formats
- Helper methods work correctly
- Format normalization handles all input types

Added parsing tests in `tests/unit/test_format_id_parsing.py`:
- `_normalize_format_value()` with various input types

## Next Steps

✅ **Client library is ready** - Already sends new format correctly
✅ **Agent implementation is complete** - Accepts both formats
🎯 **Deploy to production** - Once deployed, clients can use new format

## AdCP Spec Reference

- Format ID schema: https://adcontextprotocol.org/schemas/v1/core/format-id.json
- Creative Asset schema: https://adcontextprotocol.org/schemas/v1/core/creative-asset.json
- AdCP Version: v2.4
- Schema Version: v1
