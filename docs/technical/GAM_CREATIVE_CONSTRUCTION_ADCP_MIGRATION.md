# GAM Creative Construction - AdCP Migration Plan

## Issue Summary

**Status**: 🚨 ARCHITECTURAL ISSUE - Needs Discussion Before Implementation

The GAM adapter's creative construction code (`src/adapters/gam/managers/creatives.py`) uses a **LEGACY flat-field pattern** instead of the **AdCP v1 creative-asset spec structure**.

This was identified during gap investigation for PR #657 (creative sync and approval unification).

## Current State (Legacy Pattern)

### What We're Doing Wrong

**Current Code Pattern**:
```python
# ❌ LEGACY - Reading flat fields from asset dict
width = asset.get("width")
height = asset.get("height")
url = asset.get("url")
media_url = asset.get("media_url")
```

**Location**: `src/adapters/gam/managers/creatives.py`
- Line ~400-450: `_get_creative_dimensions()`
- Line ~500-600: `_create_hosted_asset_creative()`
- Line ~650-700: `_get_html5_source()`

### Why This is Wrong

Per **AdCP v1 creative-asset spec**, creatives should have this structure:

```json
{
  "creative_id": "creative_123",
  "name": "Banner Ad",
  "format_id": {
    "agent_url": "https://agent.example.com",
    "id": "image-asset"
  },
  "assets": {
    "main_image": {
      "url": "https://example.com/banner.jpg",
      "width": 728,
      "height": 90,
      "mime_type": "image/jpeg"
    },
    "logo": {
      "url": "https://example.com/logo.png",
      "width": 100,
      "height": 100
    }
  }
}
```

**AdCP Spec**: Assets are keyed by `asset_role` (e.g., "main_image", "logo", "cta_button").

**Our Current Code**: Expects flat fields at top level (`asset.get("url")` instead of `asset["assets"]["main_image"]["url"]`).

## Impact Assessment

### What Works Today

✅ **Database storage** - We store AdCP-compliant assets in the database
✅ **Creative sync** - We accept AdCP-compliant creatives from buyers
✅ **Creative retrieval** - We return AdCP-compliant creatives via list_creatives() (fixed in PR #657)

### What's Broken

❌ **GAM creative upload** - Can't extract asset URLs/dimensions from AdCP structure
❌ **Creative dimension extraction** - `_get_creative_dimensions()` expects flat fields
❌ **HTML5 creative construction** - `_get_html5_source()` expects flat `media_url` field
❌ **VAST creative construction** - Currently stubbed out (line 705-714)

### User Impact

**Currently**: Creative uploads to GAM may fail or use incorrect dimensions/URLs if buyer sends AdCP-compliant structure.

**Workaround**: System may fall back to legacy flat fields from `data` field (backward compatibility).

**Risk**: New clients using pure AdCP v1 structure (no legacy fields) will fail.

## Proposed Solution

### Option 1: Helper Functions with Backward Compatibility (Recommended)

Create helper functions that support BOTH patterns:

```python
def extract_asset_url(asset: dict, role: str = "main_image") -> str | None:
    """Extract asset URL from AdCP structure or legacy flat field.

    Args:
        asset: Creative asset dict (AdCP or legacy format)
        role: Asset role to extract (default: main_image)

    Returns:
        Asset URL or None if not found

    Tries:
    1. AdCP v1 structure: asset["assets"][role]["url"]
    2. Legacy flat field: asset["url"]
    """
    # Try AdCP structure first
    if "assets" in asset and isinstance(asset["assets"], dict):
        if role in asset["assets"]:
            asset_data = asset["assets"][role]
            if isinstance(asset_data, dict) and "url" in asset_data:
                return asset_data["url"]

    # Fall back to legacy flat field
    if "url" in asset:
        return asset["url"]

    return None


def extract_asset_dimensions(asset: dict, role: str = "main_image") -> tuple[int | None, int | None]:
    """Extract width/height from AdCP structure or legacy flat fields.

    Returns:
        Tuple of (width, height) or (None, None) if not found
    """
    # Try AdCP structure first
    if "assets" in asset and isinstance(asset["assets"], dict):
        if role in asset["assets"]:
            asset_data = asset["assets"][role]
            if isinstance(asset_data, dict):
                width = asset_data.get("width")
                height = asset_data.get("height")
                if width is not None and height is not None:
                    return (width, height)

    # Fall back to legacy flat fields
    width = asset.get("width")
    height = asset.get("height")
    return (width, height)
```

**Benefits**:
- ✅ Supports both AdCP v1 and legacy formats
- ✅ Gradual migration path (no breaking changes)
- ✅ Backward compatible with existing creatives
- ✅ Future-proof for AdCP v2+

**Migration Steps**:
1. Create helper functions in `src/core/helpers/creative_helpers.py`
2. Update `_get_creative_dimensions()` to use `extract_asset_dimensions()`
3. Update `_create_hosted_asset_creative()` to use `extract_asset_url()`
4. Update `_get_html5_source()` to use helpers
5. Add comprehensive unit tests
6. Update integration tests with both formats

### Option 2: Pure AdCP Migration (Breaking Change)

Remove all legacy field support and require pure AdCP v1 structure.

**Benefits**:
- ✅ Clean, spec-compliant code
- ✅ No technical debt
- ✅ Forces buyers to use correct format

**Drawbacks**:
- ❌ Breaking change for existing integrations
- ❌ Requires coordination with all buyers
- ❌ May break existing creatives in database
- ❌ Risk of production issues

**Not Recommended**: Too risky without careful rollout plan.

### Option 3: Data Migration + Pure AdCP

1. Create Alembic migration to convert legacy creatives to AdCP structure
2. Update all code to use pure AdCP structure
3. Remove legacy field support

**Benefits**:
- ✅ Clean migration path
- ✅ One-time data transformation
- ✅ No ongoing complexity

**Drawbacks**:
- ❌ Complex migration script
- ❌ Risk of data loss if migration fails
- ❌ Still breaking for external clients

**Consideration**: Could be viable if combined with deprecation period.

## Recommendation

**Go with Option 1** (Helper Functions with Backward Compatibility) because:

1. **No breaking changes** - Existing integrations continue working
2. **Future-proof** - Supports AdCP v1 structure for new clients
3. **Low risk** - Gradual migration with full backward compatibility
4. **Testable** - Can thoroughly test both code paths
5. **Reversible** - Can add more helper functions without changing architecture

**Timeline**:
- Helper functions: 1-2 days
- GAM adapter migration: 2-3 days
- Testing: 2 days
- Total: ~1 week

## Files Affected

### Core Files to Update

1. **src/core/helpers/creative_helpers.py** (NEW)
   - `extract_asset_url()`
   - `extract_asset_dimensions()`
   - `extract_asset_field()`
   - `get_primary_asset_role()` (helper to determine main asset)

2. **src/adapters/gam/managers/creatives.py** (~50 line changes)
   - Update `_get_creative_dimensions()` (line ~400-450)
   - Update `_create_hosted_asset_creative()` (line ~500-600)
   - Update `_get_html5_source()` (line ~650-700)
   - Implement `_create_vast_creative()` (line 705-714, currently stub)

3. **src/adapters/mock_ad_server.py** (minimal changes)
   - Update to use same helpers (consistency)

### Tests to Add

1. **tests/unit/test_creative_helpers.py** (NEW)
   - Test AdCP structure extraction
   - Test legacy structure extraction
   - Test fallback behavior
   - Test missing field handling

2. **tests/integration/test_gam_creative_construction_adcp.py** (NEW)
   - Test GAM creative upload with AdCP structure
   - Test GAM creative upload with legacy structure
   - Test mixed format handling
   - Test dimension extraction

## Migration Checklist

- [ ] Discuss with team - Is this the right approach?
- [ ] Create `creative_helpers.py` with extraction functions
- [ ] Write comprehensive unit tests for helpers
- [ ] Update `_get_creative_dimensions()` to use helpers
- [ ] Update `_create_hosted_asset_creative()` to use helpers
- [ ] Update `_get_html5_source()` to use helpers
- [ ] Implement VAST creative support (remove stub)
- [ ] Update Mock adapter for consistency
- [ ] Add integration tests for both formats
- [ ] Update documentation
- [ ] Code review
- [ ] QA testing with real GAM account
- [ ] Deploy to staging
- [ ] Monitor for issues
- [ ] Deploy to production

## Related Work

- **PR #657**: Creative sync and approval unification
- **Migration 4bac9efe56fc**: Added AdCP fields to database
- **Investigation**: CREATIVE_CONSTRUCTION_REVIEW.md
- **User Feedback**: "What about how we are meant to be managing and working with creatives and how they are built for gam???"

## References

- **AdCP v1 creative-asset spec**: https://adcontextprotocol.org/schemas/v1/core/creative-asset.json
- **AdCP Documentation**: https://adcontextprotocol.org/docs/
- **Current Database Schema**: `src/core/database/models.py` (Creative class, lines 331-430)
- **Current GAM Creatives Manager**: `src/adapters/gam/managers/creatives.py`

## Questions for Team

1. **Timing**: Should this be done as part of PR #657 or separate PR?
   - Recommend: Separate PR after #657 merges (too much complexity otherwise)

2. **Testing**: Do we have access to test GAM account for validation?
   - Need real GAM testing to ensure uploads work

3. **Rollout**: Should we have a feature flag for new behavior?
   - Could add `use_adcp_asset_structure` flag to tenant settings

4. **VAST Creatives**: Should we implement VAST support now or defer?
   - Currently stubbed out (line 705-714)
   - Recommend: Implement as part of this work for completeness

5. **Mock Adapter**: Should Mock adapter also use helpers?
   - Recommend: Yes, for consistency and testing

## Status

**Pending Team Discussion**

This document describes the issue and proposed solution. Next steps:
1. Team review and approval of approach
2. Create GitHub issue with this content
3. Break into smaller tasks
4. Implement in separate PR after #657 merges
