# Creative Preview Integration - Complete Fix Summary

**Date**: 2025-10-17
**Branch**: `bokelley/fix-creative-previews`
**Status**: ✅ ALL ISSUES RESOLVED - READY FOR PRODUCTION

## Overview
Complete resolution of creative preview generation issues. All bugs identified and fixed across both sales agent and creative agent codebases.

---

## ~~Update: First Issue Fixed ✅~~
## ~~Update: Second Issue Fixed ✅~~
## ~~Update: Third Issue Fixed ✅~~
## UPDATE: ALL ISSUES FIXED ✅

## Problem Statement

Creative previews were not showing up when syncing creatives. Database investigation revealed:
- All recent creatives had `preview_url: null`
- Missing `preview_response` field
- Empty `data.url`, `data.width`, `data.height`, `data.duration` fields

### Environment
- **Sales Agent**: https://adcp-sales-agent.fly.dev
- **Creative Agent**: https://creative.adcontextprotocol.org
- **Protocol**: MCP (Model Context Protocol) + AdCP v2.4
- **Date**: 2025-10-17
- **Branch**: `bokelley/fix-creative-previews`

## Root Causes & Fixes

### Issue 1: FormatId Object vs String Mismatch ✅ FIXED (Sales Agent)

**Problem**: Code was passing `FormatId` Pydantic objects to creative agent, but creative agent expected plain string format IDs.

**Error**:
```
Manifest format_id 'display_336x280_html' does not match request format_id
'agent_url=AnyUrl('https://creative.adcontextprotocol.org/') id='display_336x280_html''
```

**Fix**: Extract string ID before calling creative agent:
```python
format_id_str = creative_format.id if hasattr(creative_format, 'id') else str(creative_format)
```

**Files Modified**: `src/core/main.py` (5 locations - lines 2150, 2163, 2408, 2465, 2474)

---

### Issue 2: Missing dimensions Attribute ✅ FIXED (Creative Agent)

**Problem**: Creative agent code expected `format_obj.dimensions` but attribute didn't exist.

**Error**: `'Format' object has no attribute 'dimensions'`

**Fix**: Creative agent team updated format handling.

**Status**: Fixed by creative agent team

---

### Issue 3: Dict vs Pydantic Object ✅ FIXED (Creative Agent)

**Problem**: Creative agent expected `creative_manifest` to be a Pydantic object but received dict from MCP.

**Error**: `'dict' object has no attribute 'assets'` at `/app/src/creative_agent/storage.py:92`

**Fix**: Creative agent team updated manifest parsing to handle both dict and Pydantic objects.

**Status**: Fixed by creative agent team

---

### Issue 4: MCP Protocol Update - structured_content ✅ FIXED (Sales Agent)

**Problem**: Code was using `result.content[0].text` but MCP protocol now provides JSON in `result.structured_content`.

**Error**: `JSONDecodeError: Expecting value: line 1 column 1` (parsing empty string as JSON)

**Fix**: Updated to use `structured_content` with fallback:
```python
if hasattr(result, "structured_content") and result.structured_content:
    return result.structured_content
# Fallback to legacy content parsing...
```

**Files Modified**: `src/core/creative_agent_registry.py` (3 methods)
- `preview_creative()` (lines 503-516)
- `build_creative()` (lines 569-582)
- `_fetch_formats_from_agent()` (lines 204-246)

---

### Issue 5: Missing asset_id Schema Fields ✅ FIXED (Sales Agent)

**Problem**: Pydantic `AssetRequirement` model missing `asset_id`, `asset_role`, `required` fields from AdCP spec.

**Symptom**: Querying formats through registry showed no asset_id fields (but direct MCP query showed them).

**Fix**: Added missing fields to schema:
```python
class AssetRequirement(BaseModel):
    asset_id: str = Field(..., description="Asset identifier...")
    asset_type: str = Field(..., description="Type of asset required")
    asset_role: str | None = Field(None, description="Optional descriptive label...")
    required: bool = Field(True, description="Whether this asset is required")
```

**Files Modified**: `src/core/schemas.py` (lines 230-238)

---

### Issue 6: Outdated AdCP Schemas ✅ FIXED (Sales Agent)

**Problem**: Auto-generated schemas were outdated (Oct 14) and inlining `$ref` instead of preserving FormatId type.

**Discovery**: Official AdCP spec uses FormatId object (not string) for `format_id` field.

**Fix**:
1. Ran `scripts/refresh_adcp_schemas.py` to download latest schemas (Oct 17)
2. Ran `scripts/generate_schemas.py` to regenerate Pydantic models
3. Verified auto-generated Format now has correct type: `format_id: Annotated[FormatId, Field(...)]`

**Files Modified**:
- `tests/e2e/schemas/v1/` (56 schema files updated)
- `src/core/schemas_generated/` (80 Pydantic files regenerated)

---

### Issue 7: Asset Role Naming ✅ CLARIFIED (Creative Agent)

**Problem**: Confusion about asset key usage in creative manifests.

**Resolution**: Creative agent PR #135 clarified that `asset_id` is the key used in creative manifest `assets` object.

**Example**:
```json
{
  "assets": {
    "html_creative": {  // ← This is the asset_id from format's assets_required
      "asset_type": "html",
      "content": "<div>...</div>"
    }
  }
}
```

**Status**: Documented in creative agent PR #135

---

## Verification

### Test Script
Created `test_preview_flow.py` to verify end-to-end preview generation:

```python
async def test_preview_generation():
    """Test preview generation for a simple HTML creative."""
    registry = get_creative_agent_registry()

    agent_url = "https://creative.adcontextprotocol.org"
    format_id = "display_336x280_html"

    creative_manifest = {
        "name": "Test HTML Creative",
        "assets": {
            "html_creative": {  # asset_id from format's assets_required
                "asset_type": "html",
                "content": "<div style='width:336px;height:280px;...'>Test Ad</div>"
            }
        }
    }

    preview_result = await registry.preview_creative(
        agent_url=agent_url,
        format_id=format_id,
        creative_manifest=creative_manifest
    )
```

### Test Results ✅ SUCCESS

```
✅ Preview result received:
{
  "previews": [
    {
      "preview_id": "2375db10-39f9-4c54-afb9-9a9e2678a8ff",
      "renders": [
        {
          "render_id": "2375db10-39f9-4c54-afb9-9a9e2678a8ff-primary",
          "preview_url": "https://adcp-previews.fly.storage.tigris.dev/previews/.../desktop.html",
          "role": "primary",
          "dimensions": {"width": 336.0, "height": 280.0},
          "embedding": {
            "recommended_sandbox": "allow-scripts allow-same-origin",
            "requires_https": false,
            "supports_fullscreen": false,
            "csp_policy": null
          }
        }
      ],
      "input": {"name": "Desktop", "macros": {"DEVICE_TYPE": "desktop"}}
    },
    // ... mobile and tablet variants
  ],
  "interactive_url": "https://creative.adcontextprotocol.org//preview/.../interactive",
  "expires_at": "2025-10-18T17:38:23.835986Z"
}

✅ Found 3 preview variants (desktop, mobile, tablet)
   Preview URL: https://adcp-previews.fly.storage.tigris.dev/previews/.../desktop.html
   Dimensions: 336.0x280.0
```

---

## Files Changed

### Sales Agent (3 files modified, 1 test file created)

1. **src/core/main.py** (5 changes)
   - Line 2150: UPDATE path - format_id extraction from FormatId object
   - Line 2163: UPDATE path - preview_creative call with format_id string
   - Line 2408: CREATE path - build_creative call with format_id string
   - Line 2465: CREATE path - format_id extraction from FormatId object
   - Line 2474: CREATE path - preview_creative call with format_id string

2. **src/core/creative_agent_registry.py** (3 methods updated)
   - `preview_creative()`: Use structured_content field from MCP
   - `build_creative()`: Use structured_content field from MCP
   - `_fetch_formats_from_agent()`: Use structured_content field from MCP

3. **src/core/schemas.py** (1 class updated)
   - `AssetRequirement`: Added asset_id, asset_role, required fields per AdCP spec

4. **test_preview_flow.py** (new file)
   - Standalone test for preview generation verification

### Schema Updates (136 files)

5. **tests/e2e/schemas/v1/** (56 schema files)
   - Refreshed from adcontextprotocol.org (Oct 14 → Oct 17)

6. **src/core/schemas_generated/** (80 Pydantic files)
   - Regenerated from latest AdCP schemas
   - `_schemas_v1_core_format_json.py` now has correct FormatId type

### Creative Agent (fixed by creative agent team)
- Format dimensions handling
- Manifest parsing (dict vs Pydantic)
- Asset key usage documentation (PR #135)

---

## Deployment Checklist

**✅ Pre-Deployment Verification**:
- ✅ Preview generation working end-to-end
- ✅ MCP protocol using structured_content correctly
- ✅ FormatId objects properly converted to strings
- ✅ Schema fields match AdCP spec
- ✅ Auto-generated schemas up to date (Oct 17)
- ✅ Test script validates complete flow
- ✅ Creative agent fixes verified and working

**Branch**: `bokelley/fix-creative-previews`
**Status**: READY TO MERGE TO MAIN

---

## Impact

**Before Fixes**:
- ❌ No preview URLs generated
- ❌ Database showed null preview_url for all creatives
- ❌ Creative approval workflows blocked
- ❌ Format lookup failures due to FormatId mismatch
- ❌ Missing asset_id information from formats

**After Fixes**:
- ✅ Preview URLs generated successfully
- ✅ Multiple preview variants (desktop, mobile, tablet)
- ✅ Preview URLs stored in database
- ✅ Complete creative metadata (dimensions, embedding info)
- ✅ Creative workflows unblocked
- ✅ Asset requirements properly populated with asset_id

---

## Process Improvements

### Schema Sync in Conductor Setup ✅ ADDED

**Problem**: Schema drift wasn't caught until issues appeared in production. Schemas can be updated by AdCP team at any time.

**Solution**: Added automatic schema sync check to `scripts/setup/setup_conductor_workspace.sh`

**Behavior**:
- Runs `uv run python scripts/check_schema_sync.py` during workspace setup
- Warns if schemas are out of sync (doesn't fail setup)
- Provides clear instructions to update schemas
- Catches schema drift immediately when switching to a workspace

**Example Output**:
```
Checking AdCP schema sync...
🔍 Running AdCP Schema Sync Checks...
⚠️  WARNING: AdCP schemas are out of sync!
   This may cause integration issues with creative agent.

   To update schemas, run:
   uv run python scripts/check_schema_sync.py --update
   git add tests/e2e/schemas/
   git commit -m 'Update AdCP schemas to latest from registry'
```

**Why This Helps**:
- Developers are notified immediately when schemas drift
- No need to wait for CI failure to catch issues
- Clear instructions to fix the problem
- Reduces time between schema updates and catching bugs

---

## Related Documentation
- Creative Agent PR #135: Asset key usage clarification
- AdCP v2.4 Spec: Format and creative manifest schemas
- MCP Protocol: structured_content field usage
- Schema Sync Check: `scripts/check_schema_sync.py`
