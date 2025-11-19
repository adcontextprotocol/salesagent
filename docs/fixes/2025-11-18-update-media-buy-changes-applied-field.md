# Fix: Include changes_applied Field in update_media_buy Response

**Date**: 2025-11-18
**Issue**: `update_media_buy` response missing `changes_applied` field with creative assignment details
**Status**: ✅ Fixed

## Problem

Client reported that the `UpdateMediaBuySuccess` response was missing the `changes_applied` field in `affected_packages`. This field contains critical information about what actually changed during the update (e.g., which creative IDs were added/removed).

**What was happening:**
```json
{
  "media_buy_id": "buy_123",
  "buyer_ref": "buyer_ref_123",
  "affected_packages": [
    {
      "buyer_ref": "buyer_ref_123",
      "package_id": "pkg_1"
      // ❌ changes_applied field missing!
    }
  ]
}
```

**What clients expected (per AdCP v2.2.0):**
```json
{
  "media_buy_id": "buy_123",
  "buyer_ref": "buyer_ref_123",
  "affected_packages": [
    {
      "buyer_ref": "buyer_ref_123",
      "package_id": "pkg_1",
      "changes_applied": {
        "creative_ids": {
          "added": ["creative_1", "creative_2"],
          "removed": [],
          "current": ["creative_1", "creative_2"]
        }
      }
    }
  ]
}
```

## Root Cause

The `AffectedPackage` schema in `src/core/schemas.py` had `changes_applied` marked with `exclude=True`:

```python
class AffectedPackage(LibraryAffectedPackage):
    changes_applied: dict[str, Any] | None = Field(
        None,
        description="Internal: Detailed changes applied to package...",
        exclude=True,  # ❌ This was the problem!
    )
```

When the response was serialized via `model_dump()`, Pydantic excluded this field from the output.

**Why was it marked as exclude=True?**
- Historical assumption that `changes_applied` was an internal tracking field
- The adcp library version 2.1.0 doesn't include `changes_applied` in its `AffectedPackage` definition
- However, our documentation (docs/fixes/2025-10-23-update-media-buy-creative-assignment.md) and client expectations indicate this should be part of AdCP v2.2.0

## Solution

### 1. Removed exclude=True from changes_applied Field

**File**: `src/core/schemas.py:304-310`

**Before:**
```python
# Internal fields for tracking what changed (not in AdCP spec)
changes_applied: dict[str, Any] | None = Field(
    None,
    description="Internal: Detailed changes applied to package (creative_ids added/removed, etc.)",
    exclude=True,  # ❌ Excluded from serialization
)
```

**After:**
```python
# Per AdCP v2.2.0, changes_applied provides details about what changed
changes_applied: dict[str, Any] | None = Field(
    None,
    description="Details of changes applied to package (creative_ids added/removed/current, budget updates, etc.)",
    # ✅ No exclude=True - included in serialization
)
```

### 2. Updated Documentation

Updated class docstring to clarify this extends AdCP v2.2.0:

```python
class AffectedPackage(LibraryAffectedPackage):
    """Affected package in UpdateMediaBuySuccess response.

    Extends adcp library AffectedPackage with changes_applied field per AdCP v2.2.0.

    Library AffectedPackage required fields:
    - buyer_ref: Buyer's reference for the package
    - package_id: Publisher's package identifier

    Extended fields (AdCP v2.2.0):
    - changes_applied: Details of what changed in the package
    """
```

### 3. Updated Tests

**File**: `tests/unit/test_update_media_buy_affected_packages.py`

Updated test expectations to verify `changes_applied` is **included** (not excluded) in serialization:

```python
def test_response_serialization_includes_affected_packages():
    """Test that UpdateMediaBuySuccess serializes affected_packages correctly per AdCP v2.2.0."""
    # ... setup code ...

    # Test 1: Regular serialization (AdCP v2.2.0 compliant)
    response_dict = response.model_dump()

    pkg = response_dict["affected_packages"][0]

    # Internal fields should be EXCLUDED
    assert "buyer_package_ref" not in pkg, "Internal field should be excluded"

    # AdCP v2.2.0 fields should be PRESENT
    assert pkg["buyer_ref"] == "buyer_ref_serialization"
    assert pkg["package_id"] == "pkg_1"
    assert "changes_applied" in pkg, "changes_applied should be included per AdCP v2.2.0"
    assert pkg["changes_applied"]["creative_ids"]["added"] == ["creative_a"]
```

## Testing

### Unit Tests
```bash
uv run pytest tests/unit/test_update_media_buy_affected_packages.py -v
# ✅ 4/4 tests passed
```

**Tests verify:**
- ✅ `changes_applied` is present in serialized response
- ✅ `changes_applied.creative_ids` contains `added`, `removed`, `current` arrays
- ✅ Internal fields like `buyer_package_ref` are still excluded
- ✅ Creative replacement workflow shows both added and removed IDs

### Manual Verification
```python
from src.core.schemas import AffectedPackage, UpdateMediaBuySuccess

response = UpdateMediaBuySuccess(
    media_buy_id="test_buy",
    buyer_ref="buyer_ref",
    affected_packages=[
        AffectedPackage(
            buyer_ref="buyer_ref",
            package_id="pkg_1",
            changes_applied={
                "creative_ids": {
                    "added": ["creative_1", "creative_2"],
                    "removed": [],
                    "current": ["creative_1", "creative_2"]
                }
            }
        )
    ]
)

# Serialize and verify
serialized = response.model_dump()
assert "changes_applied" in serialized["affected_packages"][0]  # ✅ Present!
```

## Impact

### Before Fix
- ❌ Clients received `affected_packages` with only `buyer_ref` and `package_id`
- ❌ No visibility into what actually changed during the update
- ❌ Clients couldn't determine which creatives were added/removed without additional API calls

### After Fix
- ✅ Clients receive full `changes_applied` details
- ✅ Clients know exactly which creative IDs were added, removed, and current state
- ✅ Compliant with AdCP v2.2.0 expectations
- ✅ Better client experience - no additional API calls needed

### Affected Operations
- ✅ MCP `update_media_buy` tool
- ✅ A2A `update_media_buy` endpoint
- ✅ Any client consuming `UpdateMediaBuySuccess` responses

## Sales Agent Extension

**Important Context:**
- The adcp library version 2.6.0 does NOT include `changes_applied` in `AffectedPackage`
- Base library `AffectedPackage` only has: `buyer_ref` and `package_id`
- Our sales agent extends `AffectedPackage` to add `changes_applied` field

**Why We Extend:**
- Provides clients with valuable change details (creative_ids added/removed/current, budget updates, etc.)
- Makes the API more useful - clients know exactly what changed without additional queries
- Maintains backward compatibility (field is optional)
- Clients who don't need change details can ignore the field

**Our Approach:**
- Extend the library's `AffectedPackage` class to add `changes_applied` field
- This is documented as a sales agent extension, not part of the base adcp library
- The field is optional, so clients using base library expectations still work

## Files Changed

- `src/core/schemas.py` (line 293-313): Removed `exclude=True` from `changes_applied` field
- `tests/unit/test_update_media_buy_affected_packages.py`: Updated test expectations
- `docs/fixes/2025-11-18-update-media-buy-changes-applied-field.md` (new): This document

## References

- Original creative assignment implementation: `docs/fixes/2025-10-23-update-media-buy-creative-assignment.md`
- Related code: `src/core/tools/media_buy_update.py` (lines 541, 760-768, 833, 911-913)
- Tests: `tests/unit/test_update_media_buy_affected_packages.py`
- AdCP library: `adcp>=2.5.0` (currently 2.6.0)
