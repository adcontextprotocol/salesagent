# AdCP v2.4 Format ID Namespacing Implementation

## Overview

Implemented **mandatory** `agent_url` namespacing for all `format_id` values per AdCP v2.4 spec. String `format_id` values are **no longer supported** - all formats must include both `agent_url` and `id` fields.

## Critical Changes

### 1. Database Schema

**Migration: `f2addf453200_add_agent_url_to_creatives_and_products.py`**

```sql
-- Add agent_url column to creatives table
ALTER TABLE creatives ADD COLUMN agent_url VARCHAR(500) NOT NULL;

-- Backfill existing creatives with default agent URL
UPDATE creatives
SET agent_url = 'https://creative.adcontextprotocol.org'
WHERE agent_url IS NULL;

-- Add composite index for format namespace lookups
CREATE INDEX idx_creatives_format_namespace ON creatives (agent_url, format);

-- Drop deprecated creative_formats table
DROP TABLE creative_formats;
```

**Why drop creative_formats?**
- Sales agents no longer maintain custom formats
- All formats are fetched from creative agents via AdCP
- Table was deprecated and causing confusion

### 2. Pydantic Schema Validation

**Strict Validation - NO String Format IDs**

```python
class FormatId(BaseModel):
    """AdCP v2.4 format identifier with required namespace."""
    agent_url: str = Field(..., description="URL of the agent defining this format")
    id: str = Field(..., pattern=r"^[a-zA-Z0-9_-]+$")

class Creative(BaseModel):
    format: FormatId = Field(alias="format_id")  # MUST be FormatId object

    @model_validator(mode="before")
    @classmethod
    def validate_format_id(cls, values):
        """Reject string format_id - agent_url is mandatory."""
        format_val = values.get("format_id") or values.get("format")
        if isinstance(format_val, str):
            raise ValueError(
                f"format_id must be an object with 'agent_url' and 'id' fields. "
                f"Got string: '{format_val}'"
            )
        return values
```

### 3. Code Changes

**New Helper Functions:**

```python
def _extract_format_namespace(format_value: Any) -> tuple[str, str]:
    """Extract (agent_url, format_id) from format_id field.

    Raises ValueError if format_id is a string or missing required fields.
    """

def _normalize_format_value(format_value: Any) -> str:
    """Legacy compatibility - extracts just the format ID string.

    New code should use _extract_format_namespace() instead.
    """
```

**Updated sync_creatives:**
- Extracts both `agent_url` and `format_id` when creating/updating creatives
- Stores both in database
- Rejects string `format_id` values

### 4. Products Table Migration

**TODO**: Products table stores formats in JSONB `formats` column. Need data migration to convert:

```json
// OLD (deprecated)
{
  "formats": ["display_300x250", "video_640x480"]
}

// NEW (required)
{
  "formats": [
    {"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250"},
    {"agent_url": "https://creative.adcontextprotocol.org", "id": "video_640x480"}
  ]
}
```

**Migration script needed**: `scripts/migrate_product_formats.py`

## Breaking Changes

### ❌ These Will Be Rejected

```json
// String format_id (NO LONGER SUPPORTED)
{
  "creative_id": "c1",
  "format_id": "display_300x250"  ❌
}

// Missing agent_url
{
  "creative_id": "c1",
  "format_id": {"id": "display_300x250"}  ❌
}
```

### ✅ Correct Format

```json
{
  "creative_id": "c1",
  "format_id": {
    "agent_url": "https://creative.adcontextprotocol.org",
    "id": "display_300x250"
  }
}
```

## Why Agent URL Matters

### Problem: Format ID Collisions

Without `agent_url`, formats from different providers collide:

```
Agent A: display_300x250 (supports VAST)
Agent B: display_300x250 (supports HTML5 only)

// Which one? No way to tell!
format_id: "display_300x250"  ❌
```

### Solution: Namespacing

```json
// Unambiguous - we know exactly which agent provides this format
{
  "agent_url": "https://agent-a.example.com",
  "id": "display_300x250"
}
```

This enables:
- Multiple creative agents providing formats
- Format version control (agent can evolve formats)
- Clear format ownership and capabilities
- Proper format resolution when creating creatives

## Testing

### Unit Tests

**`tests/unit/test_format_id.py`**: (14 tests, all passing)
- FormatId model validation
- Creative rejects string format_id
- Creative requires agent_url
- Helper function validation

**`tests/unit/test_format_id_parsing.py`**: (6 tests, all passing)
- `_extract_format_namespace()` functionality
- String rejection validation
- Missing field detection

### Integration Tests

**TODO**: Need to update these to use new format:
- All sync_creatives tests
- Creative creation/update flows
- Product catalog tests

## Migration Path

### For Existing Data

1. **Run Database Migration**:
   ```bash
   uv run python migrate.py
   ```
   - Adds `agent_url` column
   - Backfills with `https://creative.adcontextprotocol.org`
   - Drops `creative_formats` table

2. **Migrate Product Formats** (TODO):
   ```bash
   uv run python scripts/migrate_product_formats.py
   ```
   - Converts string format IDs to objects in products table
   - Updates all JSONB `formats` arrays

### For Client Libraries

Clients **must** send format_id as object:

```python
# ✅ CORRECT
creative = {
    "creative_id": "c1",
    "name": "My Creative",
    "format_id": {
        "agent_url": "https://creative.adcontextprotocol.org",
        "id": "display_300x250"
    },
    "assets": {...}
}
```

## Next Steps

1. ✅ Database migration created
2. ✅ Models updated with validation
3. ✅ sync_creatives handles agent_url
4. ✅ Unit tests passing
5. ⏳ TODO: Product formats data migration
6. ⏳ TODO: Update integration tests
7. ⏳ TODO: Update existing test data/fixtures
8. ⏳ TODO: Document in AdCP changelog

## AdCP Spec Reference

- Format ID Schema: https://adcontextprotocol.org/schemas/v1/core/format-id.json
- Creative Asset Schema: https://adcontextprotocol.org/schemas/v1/core/creative-asset.json
- AdCP Version: v2.4
- Schema Version: v1
