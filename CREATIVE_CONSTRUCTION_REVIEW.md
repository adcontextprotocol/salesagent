# GAM Creative Construction Review - Asset Handling Analysis

**Date**: 2025-10-28
**Status**: ⚠️ LEGACY PATTERN DETECTED - Needs Migration to AdCP-Compliant Assets

## Executive Summary

We are currently using **legacy creative fields** (`url`, `media_url`, `width`, `height`) to build GAM creatives, not the new AdCP-compliant `assets` structure. This is a **schema compliance issue** that needs to be addressed to follow the official AdCP v1 specification.

---

## Current Architecture

### 1. **AdCP Schema Structure (Official Spec)**

Per the AdCP v1 specification at https://adcontextprotocol.org/schemas/v1/core/creative-asset.json:

```python
class CreativeAsset(AdCPBaseModel):
    """AdCP v1 creative-asset schema - official specification."""
    creative_id: str
    name: str
    format_id: FormatId
    assets: dict[str, Any]  # ⭐ NEW: Typed assets by role
    inputs: list[CreativeAssetInput] | None
    tags: list[str] | None
    approved: bool | None
```

**Asset Types** (per AdCP spec):
- `ImageAsset`: Has `url`, `width`, `height`, `format`, `alt_text`
- `VideoAsset`: Has `url`, `width`, `height`, `duration_ms`, `format`, `bitrate_kbps`
- `AudioAsset`: Has `url`, `duration_ms`, `format`, `bitrate_kbps`
- `TextAsset`: Has `text`, `max_length`
- `HtmlAsset`: Has `html`
- `CssAsset`: Has `css`
- `JavascriptAsset`: Has `javascript`, `sandbox_compatible`
- `UrlAsset`: Has `url`, `tracking_parameters`

### 2. **Current Implementation (Legacy Pattern)**

**File**: `src/core/tools/creatives.py` (lines 1326-1348)

```python
# Build asset dict for adapter (following add_creative_assets signature)
asset_dict = {
    "creative_id": db_creative.creative_id,
    "id": db_creative.creative_id,
    "name": db_creative.name,
    "format": db_creative.format,
    "package_assignments": [assignment.package_id],
}

# Add media data from creative.data field
if db_creative.data:
    if db_creative.data.get("url"):
        asset_dict["media_url"] = db_creative.data["url"]  # ⚠️ LEGACY
    if db_creative.data.get("width"):
        asset_dict["width"] = db_creative.data["width"]  # ⚠️ LEGACY
    if db_creative.data.get("height"):
        asset_dict["height"] = db_creative.data["height"]  # ⚠️ LEGACY
    if db_creative.data.get("duration"):
        asset_dict["duration"] = db_creative.data["duration"]  # ⚠️ LEGACY
    if db_creative.data.get("click_url"):
        asset_dict["click_url"] = db_creative.data["click_url"]  # ⚠️ LEGACY
```

**Problem**: We're extracting flat fields from `db_creative.data` instead of using structured `assets` objects.

### 3. **GAM Creative Construction (Legacy Field Access)**

**File**: `src/adapters/gam/managers/creatives.py`

#### Dimension Extraction (lines 549-580)
```python
def _get_creative_dimensions(self, asset: dict[str, Any], placeholders: list[dict] = None) -> tuple[int, int]:
    # Try explicit width/height first
    if asset.get("width") and asset.get("height"):  # ⚠️ LEGACY top-level fields
        return int(asset["width"]), int(asset["height"])

    # Try to parse from format string
    format_str = asset.get("format", "")  # ⚠️ LEGACY top-level format
    # ... parse dimensions from format string

    # Default fallback
    return 300, 250
```

#### URL Extraction (lines 434-452, 485-547)
```python
# Third-party creative
def _create_third_party_creative(self, asset: dict[str, Any]) -> dict[str, Any]:
    # Use snippet if available (AdCP v1.3+), otherwise fall back to URL
    snippet = asset.get("snippet")  # ⚠️ LEGACY top-level field
    if not snippet:
        snippet = asset.get("url", "")  # ⚠️ LEGACY top-level field

# Hosted asset creative (image/video)
def _create_hosted_asset_creative(self, asset: dict[str, Any]) -> dict[str, Any]:
    url = asset.get("url")  # ⚠️ LEGACY top-level field
    if not url:
        raise Exception("No URL found for hosted asset creative")

    click_url = asset.get("clickthrough_url") or asset.get("landing_url") or asset.get("click_url") or url  # ⚠️ LEGACY

# HTML5 creative
def _get_html5_source(self, asset: dict[str, Any]) -> str:
    if asset.get("media_data"):  # ⚠️ LEGACY
        # ... decode base64
    if asset.get("media_url"):  # ⚠️ LEGACY
        return f'<iframe src="{asset["media_url"]}" ...></iframe>'
    url = asset.get("url", "")  # ⚠️ LEGACY
```

#### Creative Type Detection (lines 240-287)
```python
def _get_creative_type(self, asset: dict[str, Any]) -> str:
    # Check AdCP v1.3+ fields first
    if asset.get("snippet") and asset.get("snippet_type"):  # ⚠️ LEGACY top-level fields
        # ...
    elif asset.get("template_variables"):  # ⚠️ LEGACY top-level field
        return "native"
    elif asset.get("media_url") or asset.get("media_data"):  # ⚠️ LEGACY top-level fields
        # ...
    else:
        url = asset.get("url", "")  # ⚠️ LEGACY top-level field
```

---

## Issues with Current Implementation

### ❌ Schema Compliance Issues

1. **Not Reading from `assets` Field**
   - Current code reads `asset.get("url")`, `asset.get("width")`, etc.
   - Should read from `asset["assets"]["main_image"].url`, `asset["assets"]["main_image"].width`
   - AdCP spec defines assets as typed objects by role, not flat fields

2. **Legacy Field Dependencies**
   - Code depends on top-level `url`, `media_url`, `snippet`, `template_variables`
   - These are NOT in the official AdCP v1 creative-asset schema
   - Only `assets` dictionary is spec-compliant

3. **Mixed Schema Versions**
   - Comments reference "AdCP v1.3+" but implementation uses pre-v1 patterns
   - Current schema tests (`test_adcp_creative_asset_schema.py`) validate NEW structure
   - But production code still uses OLD structure

### ⚠️ Backward Compatibility Concerns

The code does have some asset-aware logic:
```python
# Line 401-404 in creatives.py
if creative.get("assets"):
    data["assets"] = creative.get("assets")
```

But GAM adapter doesn't know how to use it:
- GAM manager looks for `asset.get("url")` (top-level)
- NOT `asset["assets"]["main_image"]["url"]` (spec-compliant)

---

## Recommended Migration Path

### Phase 1: Asset Extraction Helpers (Non-Breaking)

**Goal**: Add helper functions to extract data from both legacy and new formats.

**File**: `src/adapters/gam/managers/creatives.py`

```python
def _extract_dimensions_from_assets(self, asset: dict[str, Any]) -> tuple[int, int] | None:
    """Extract dimensions from AdCP-compliant assets structure.

    Args:
        asset: Asset dictionary with 'assets' field

    Returns:
        (width, height) tuple or None if not found
    """
    if not asset.get("assets"):
        return None

    # Try to find first asset with dimensions
    for role, asset_obj in asset["assets"].items():
        if isinstance(asset_obj, dict):
            width = asset_obj.get("width")
            height = asset_obj.get("height")
            if width and height:
                return int(width), int(height)

    return None

def _extract_url_from_assets(self, asset: dict[str, Any], role: str = None) -> str | None:
    """Extract URL from AdCP-compliant assets structure.

    Args:
        asset: Asset dictionary with 'assets' field
        role: Optional role to look for (e.g., "main_image", "click_url")

    Returns:
        URL string or None if not found
    """
    if not asset.get("assets"):
        return None

    # If role specified, look for that specific asset
    if role and role in asset["assets"]:
        asset_obj = asset["assets"][role]
        if isinstance(asset_obj, dict):
            return asset_obj.get("url")

    # Otherwise, try to find first asset with a URL
    for role_name, asset_obj in asset["assets"].items():
        if isinstance(asset_obj, dict) and asset_obj.get("url"):
            return asset_obj["url"]

    return None

def _get_creative_dimensions(self, asset: dict[str, Any], placeholders: list[dict] = None) -> tuple[int, int]:
    """Get creative dimensions from asset (supports both legacy and new formats).

    Args:
        asset: Creative asset dictionary
        placeholders: Optional list of placeholders for validation

    Returns:
        Tuple of (width, height)
    """
    # TRY NEW: AdCP-compliant assets structure first
    dimensions = self._extract_dimensions_from_assets(asset)
    if dimensions:
        return dimensions

    # FALLBACK: Legacy top-level width/height
    if asset.get("width") and asset.get("height"):
        return int(asset["width"]), int(asset["height"])

    # FALLBACK: Parse from format string
    format_str = asset.get("format", "")
    if format_str:
        # ... existing parsing logic

    # Default fallback
    logger.warning(
        f"Could not determine dimensions for creative {asset.get('creative_id', 'unknown')}, "
        f"using 300x250 default"
    )
    return 300, 250
```

### Phase 2: Update Creative Construction Methods

Update each `_create_*_creative()` method to use helper functions:

```python
def _create_hosted_asset_creative(self, asset: dict[str, Any]) -> dict[str, Any]:
    """Create a hosted asset (image/video) creative for GAM."""
    width, height = self._get_creative_dimensions(asset)

    # TRY NEW: Get URL from assets structure
    url = self._extract_url_from_assets(asset, role="main_image") or \
          self._extract_url_from_assets(asset, role="main_video") or \
          self._extract_url_from_assets(asset)

    # FALLBACK: Legacy top-level URL
    if not url:
        url = asset.get("url")

    if not url:
        raise Exception("No URL found for hosted asset creative")

    # TRY NEW: Get click URL from assets structure
    click_url = self._extract_url_from_assets(asset, role="click_url") or \
                self._extract_url_from_assets(asset, role="landing_url")

    # FALLBACK: Legacy top-level click URL fields
    if not click_url:
        click_url = asset.get("clickthrough_url") or asset.get("landing_url") or asset.get("click_url") or url

    # ... rest of method
```

### Phase 3: Update Asset Dict Construction

**File**: `src/core/tools/creatives.py` (lines 1326-1348)

```python
# Build asset dict for adapter (following add_creative_assets signature)
asset_dict = {
    "creative_id": db_creative.creative_id,
    "id": db_creative.creative_id,
    "name": db_creative.name,
    "format": db_creative.format,
    "package_assignments": [assignment.package_id],
}

# NEW: Pass assets structure if available (AdCP-compliant)
if db_creative.assets:
    asset_dict["assets"] = db_creative.assets

# LEGACY: Add media data from creative.data field (backward compatibility)
if db_creative.data:
    if db_creative.data.get("url"):
        asset_dict["media_url"] = db_creative.data["url"]
    # ... rest of legacy fields
```

### Phase 4: Deprecation Timeline

1. **v2.5** (Next Release): Add helper functions, support both formats
2. **v2.6** (3 months): Deprecation warnings for legacy format
3. **v3.0** (6 months): Remove legacy format support entirely

---

## Testing Requirements

### Unit Tests to Add

1. **Test Asset Extraction Helpers**
   ```python
   def test_extract_dimensions_from_assets():
       """Test dimension extraction from AdCP-compliant assets."""
       asset = {
           "creative_id": "test_123",
           "assets": {
               "main_image": {
                   "url": "https://example.com/image.jpg",
                   "width": 728,
                   "height": 90
               }
           }
       }
       manager = GAMCreativesManager(...)
       width, height = manager._get_creative_dimensions(asset)
       assert width == 728
       assert height == 90
   ```

2. **Test Legacy Fallback**
   ```python
   def test_legacy_dimensions_still_work():
       """Test that legacy top-level width/height still works."""
       asset = {
           "creative_id": "test_123",
           "width": 300,
           "height": 250
       }
       manager = GAMCreativesManager(...)
       width, height = manager._get_creative_dimensions(asset)
       assert width == 300
       assert height == 250
   ```

3. **Test Mixed Format**
   ```python
   def test_prefers_new_format_over_legacy():
       """Test that new assets format takes precedence."""
       asset = {
           "creative_id": "test_123",
           "width": 300,  # Legacy
           "height": 250,  # Legacy
           "assets": {
               "main_image": {
                   "url": "https://example.com/image.jpg",
                   "width": 728,  # New - should take precedence
                   "height": 90
               }
           }
       }
       manager = GAMCreativesManager(...)
       width, height = manager._get_creative_dimensions(asset)
       assert width == 728  # New format wins
       assert height == 90
   ```

### Integration Tests

1. Test full creative sync with new `assets` structure
2. Test GAM creative creation with both legacy and new formats
3. Test backward compatibility with existing creatives in database

---

## Impact Assessment

### ✅ Benefits of Migration

1. **AdCP Spec Compliance**: Follow official v1 specification exactly
2. **Type Safety**: Structured assets with typed objects (ImageAsset, VideoAsset, etc.)
3. **Extensibility**: Easy to add new asset types without schema changes
4. **Role-Based Assets**: Multiple assets per creative (e.g., thumbnail + video + click_url)

### ⚠️ Risks

1. **Breaking Change**: Existing creatives may not have `assets` field populated
2. **Migration Effort**: Need to update existing database records
3. **Adapter Compatibility**: All adapters (GAM, Mock, Kevel, Triton) need updates

### 📊 Estimated Effort

- **Phase 1** (Helper Functions): 1-2 days
- **Phase 2** (Creative Construction): 2-3 days
- **Phase 3** (Asset Dict Updates): 1 day
- **Testing**: 2-3 days
- **Total**: ~1 week of development time

---

## Conclusion

**Current Status**: ⚠️ **USING LEGACY PATTERN**

We are extracting creative data from:
- ❌ `asset.get("url")` (top-level)
- ❌ `asset.get("width")` (top-level)
- ❌ `asset.get("media_url")` (top-level)
- ❌ `db_creative.data["url"]` (legacy data field)

**Should Be Using**:
- ✅ `asset["assets"]["main_image"]["url"]` (spec-compliant)
- ✅ `asset["assets"]["main_image"]["width"]` (spec-compliant)
- ✅ Typed asset objects (ImageAsset, VideoAsset, etc.)

**Recommendation**: Implement Phase 1 immediately (helper functions with fallbacks) to support both formats during migration period. This allows gradual migration without breaking existing functionality.

---

## References

1. **AdCP Spec**: https://adcontextprotocol.org/schemas/v1/core/creative-asset.json
2. **Schema Models**: `/src/core/schemas.py` (lines 1303-1460)
3. **GAM Manager**: `/src/adapters/gam/managers/creatives.py`
4. **Creative Tools**: `/src/core/tools/creatives.py` (lines 1326-1348)
5. **Tests**: `/tests/unit/test_adcp_creative_asset_schema.py`
