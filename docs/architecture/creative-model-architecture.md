# Creative Model Architecture

## Overview

The `Creative` class in `src/core/schemas.py` is a **hybrid model** that serves multiple purposes in the sales agent. This document explains why it has more fields than the official AdCP spec, and why many fields are optional.

## The Problem

The official [AdCP v1 CreativeAsset spec](https://adcontextprotocol.org/schemas/v1/core/creative-asset.json) defines only 7 fields:

**Required:**
- `creative_id`
- `name`
- `format_id`
- `assets`

**Optional:**
- `inputs` (for generative formats)
- `tags`
- `approved`

However, the sales agent needs to:
1. **Accept** AdCP-compliant creative input (sync_creatives, inline creatives in create_media_buy)
2. **Store** additional metadata (principal_id, timestamps, status, approval workflow)
3. **Process** various creative types (hosted assets, third-party tags, VAST, native)
4. **Return** AdCP-compliant responses (filtering out internal fields)

## The Solution: Hybrid Model

The `Creative` class is a **hybrid model** that supports all these use cases:

### 1. AdCP Input Validation ✅

When receiving creatives from buyers:
```python
# Buyer sends AdCP-compliant creative
creative = Creative(
    creative_id="banner_123",
    name="Example Banner",
    format_id=FormatId(agent_url="https://...", id="display_300x250"),
    assets={
        "banner_image": {
            "url": "https://example.com/image.png",
            "width": 300,
            "height": 250
        }
    }
)
# ✅ Works! Internal fields (principal_id, created_at, etc.) are optional
```

### 2. Internal Storage 📦

When storing in database, sales agent adds internal fields:
```python
creative = Creative(
    # AdCP fields from buyer
    creative_id="banner_123",
    name="Example Banner",
    format_id=...,
    assets={...},
    # Internal fields added by sales agent
    principal_id="principal_abc",
    tenant_id="tenant_123",
    created_at=datetime.utcnow(),
    updated_at=datetime.utcnow(),
    status="pending"
)
```

### 3. Response Serialization 📤

When returning creatives in responses, internal fields are filtered:
```python
# model_dump() automatically excludes internal fields
response_data = creative.model_dump(exclude_none=True)
# Result: Only AdCP-spec fields, no principal_id/created_at/etc.
```

## Field Categories

### AdCP v1 Spec Fields (Official)
- ✅ `creative_id` (required)
- ✅ `name` (required)
- ✅ `format_id` (required)
- ✅ `assets` (required)
- ✅ `inputs` (optional)
- ✅ `tags` (optional)
- ✅ `approved` (optional)

### Internal Fields (Sales Agent)
- ⚙️ `principal_id` - Associates creative with advertiser
- ⚙️ `tenant_id` - Multi-tenancy isolation
- ⚙️ `created_at` - Audit trail
- ⚙️ `updated_at` - Audit trail
- ⚙️ `status` - Approval workflow (pending/approved/rejected)
- ⚙️ `platform_id` - Ad server platform ID (GAM creative ID, etc.)
- ⚙️ `review_feedback` - Human/AI review comments
- ⚙️ `compliance` - Compliance review results

### Extension Fields (Backward Compatibility)
- 🔧 `url` / `content_uri` - Legacy field, now use `assets` dict
- 🔧 `media_url` - Alternative URL
- 🔧 `click_url` - Click-through URL (should be URL asset in `assets` dict)
- 🔧 `width`, `height`, `duration` - Content dimensions (should be in asset objects)
- 🔧 `snippet`, `snippet_type` - Third-party tag support
- 🔧 `template_variables` - Native ad support
- 🔧 `delivery_settings` - Platform-specific config

## Why Fields Are Optional

### Problem: Chicken-and-Egg with Required Fields

If `principal_id`, `created_at`, etc. were **required**, buyers would have to provide them:
```python
# ❌ BAD: Buyer has to know internal sales agent details
creative = Creative(
    creative_id="banner_123",
    name="Example",
    format_id=...,
    assets={...},
    principal_id="???",  # Buyer doesn't know this!
    created_at="???",     # Buyer doesn't know this!
    tenant_id="???"       # Buyer doesn't know this!
)
```

This violates the AdCP spec - buyers should only send `creative_id`, `name`, `format_id`, and `assets`.

### Solution: Make Internal Fields Optional

By making internal fields optional, we support both use cases:
```python
# ✅ GOOD: Buyer sends only AdCP fields (inline creative)
creative_from_buyer = Creative(
    creative_id="banner_123",
    name="Example",
    format_id=...,
    assets={...}
    # principal_id, created_at, etc. are None
)

# ✅ GOOD: Sales agent adds internal fields when storing
creative_for_storage = Creative(
    creative_id="banner_123",
    name="Example",
    format_id=...,
    assets={...},
    principal_id="principal_abc",  # Added by sales agent
    created_at=datetime.utcnow(),   # Added by sales agent
    status="pending"                # Added by sales agent
)
```

## Database Storage

The database model (`src/core/database/models.py::Creative`) stores:
- Core fields: `creative_id`, `tenant_id`, `principal_id`, `name`, `agent_url`, `format`, `status`
- JSON blob: `data` field containing all creative content (assets, dimensions, etc.)
- Metadata: `created_at`, `updated_at`, `approved_at`, `approved_by`, `strategy_id`

The Pydantic `Creative` model is converted to/from the database model when storing/retrieving.

## Response Serialization

The `Creative.model_dump()` method automatically excludes internal fields:
```python
def model_dump(self, **kwargs):
    """Override to provide AdCP-compliant responses while preserving internal fields."""
    exclude = kwargs.get("exclude", set())
    if isinstance(exclude, set):
        exclude.update({
            "principal_id",
            "group_id",
            "created_at",
            "updated_at",
            "has_macros",
            "macro_validation",
            "asset_mapping",
            "metadata",
            # ... other internal fields
        })
        kwargs["exclude"] = exclude
    return super().model_dump(**kwargs)
```

This ensures:
- ✅ Input: Accepts AdCP-compliant creatives (only spec fields)
- ✅ Storage: Adds internal fields for processing
- ✅ Output: Returns AdCP-compliant responses (filters internal fields)

## Why Not Separate Models?

You might wonder: "Why not have separate models for input/storage/output?"

**Answer:** We could, but it would create significant complexity:
- Need conversion functions between 3+ models
- Database ORM mappings become more complex
- Type hints become harder to manage
- More code duplication

The hybrid model approach is pragmatic:
- ✅ Single model reduces complexity
- ✅ Optional fields support both use cases
- ✅ `model_dump()` handles response filtering
- ✅ Clear documentation explains the design

## GitHub Issue #703

This architecture directly addresses [issue #703](https://github.com/adcontextprotocol/salesagent/issues/703), where `sync_creatives` was rejecting AdCP-compliant examples from the docs.

**Root cause:** Internal fields (`principal_id`, `created_at`, etc.) were required, forcing buyers to provide sales-agent-internal values.

**Fix:** Made internal fields optional, allowing buyers to send pure AdCP CreativeAsset objects. Sales agent adds internal fields during processing.

## Future Considerations

If the codebase grows significantly, we might refactor to:
1. **`CreativeAsset`** - Pure AdCP input model (7 fields only)
2. **`CreativeRecord`** - Internal storage model (adds metadata)
3. **`CreativeResponse`** - Response model (AdCP fields + extensions)

But for now, the hybrid model is the right balance of simplicity and functionality.

## AdCP v1 Asset Types and Adapter Mappings

### Asset Type Reference (from AdCP v1 spec)

The `assets` field in the Creative model is a dictionary of asset objects, each conforming to one of these AdCP v1 asset schemas:

#### 1. **Image Asset** (`image-asset.json`)
- **Required**: `url`
- **Optional**: `width`, `height`, `format`, `alt_text`
- **Use case**: Static image creatives (banners, display ads)

#### 2. **Video Asset** (`video-asset.json`)
- **Required**: `url`
- **Optional**: `width`, `height`, `duration_ms`, `format`, `bitrate_kbps`
- **Use case**: Hosted video creatives (MP4, WebM)

#### 3. **HTML Asset** (`html-asset.json`)
- **Required**: `content`
- **Optional**: `version`
- **Use case**: HTML5 banner ads, rich media

#### 4. **JavaScript Asset** (`javascript-asset.json`)
- **Required**: `content`
- **Optional**: `module_type` (esm, commonjs, script)
- **Use case**: JavaScript-based ads, interactive creatives

#### 5. **VAST Asset** (`vast-asset.json`)
- **Required**: `url` XOR `content` (exactly one)
- **Optional**: `vast_version`, `vpaid_enabled`, `duration_ms`, `tracking_events`
- **Use case**: Third-party video ad serving

#### 6. **URL Asset** (`url-asset.json`)
- **Required**: `url`
- **Optional**: `url_type` (clickthrough, tracker_pixel, tracker_script), `description`
- **Use cases**:
  - `clickthrough`: Landing page URL (where user goes on click)
  - `tracker_pixel`: Impression/event tracking pixel
  - `tracker_script`: Measurement SDK (OMID, verification)

### Conversion Logic for Ad Server Adapters

When converting AdCP creatives to ad server formats (GAM, Kevel, etc.), the adapter uses these mappings:

#### GAM/Google Ad Manager

**Image/Video Creatives** (hosted assets):
```
AdCP assets → GAM format:
  assets["banner_image"].url → media_url, url
  assets["banner_image"].width → width
  assets["banner_image"].height → height
  assets["video_file"].duration_ms → duration (convert ms to seconds)
  assets[*].url_type="clickthrough" → click_url
```

**HTML/JavaScript Creatives** (third-party):
```
AdCP assets → GAM format:
  assets[*].content (where type=html|javascript) → snippet
  snippet_type = "html" or "javascript"
```

**VAST Creatives** (video third-party):
```
AdCP assets → GAM format:
  assets[*].content (where type=vast) → snippet
  assets[*].url (where type=vast) → snippet (if no content)
  snippet_type = "vast_xml" (if content) or "vast_url" (if url)
```

**Tracking URLs**:
```
AdCP assets → GAM format:
  assets[*].url_type="tracker_pixel" → delivery_settings.tracking_urls.impression[]
  assets[*].url_type="clickthrough" → click_url (landing page, not tracking)
```

### Asset Role Naming Conventions

When processing creatives, the adapter looks for assets using these common role names (in priority order):

**Primary asset detection by format type:**
- **Display formats** (`display_*`): `banner_image`, `image`, `main`, `creative`, `content`
- **Video formats** (`video_*`): `video_file`, `video`, `main`, `creative`
- **Native formats** (`native_*`): `main`, `creative`, `content`

**Special-purpose assets:**
- `html_content`, `javascript_code` - Code assets
- `vast_tag`, `vast` - VAST third-party tags
- `click_url`, `clickthrough` - Landing page URL
- `impression_tracker`, `tracker_*` - Tracking pixels

### Important Notes

1. **Duration field**: AdCP uses `duration_ms` (milliseconds), GAM uses seconds - conversion happens in adapter
2. **VAST oneOf**: VAST must have EITHER url OR content, never both (per AdCP spec)
3. **URL type detection**: Use `url_type` field to distinguish clickthrough from trackers
4. **Multiple trackers**: Multiple impression trackers are collected into an array
5. **No asset_type field**: AdCP doesn't have top-level asset_type - type is inferred from format_id prefix (display_*, video_*, native_*)
6. **Clickthrough vs Tracking**: Clickthrough URLs (`url_type="clickthrough"`) go to `click_url` for landing pages, NOT to tracking_urls

## Related Files

- `src/core/schemas.py::Creative` - The hybrid model
- `src/core/database/models.py::Creative` - Database ORM model
- `src/core/tools/creatives.py::_sync_creatives_impl()` - Handles creative processing
- `src/core/helpers/creative_helpers.py::_convert_creative_to_adapter_asset()` - AdCP to adapter conversion
- `schemas/v1/_schemas_v1_core_creative-asset_json.json` - Official AdCP spec
- `tests/unit/test_adcp_contract.py` - AdCP compliance tests
- `tests/unit/test_creative_conversion_assets.py` - Asset conversion tests

## Summary

The `Creative` class is intentionally designed as a hybrid model to:
- ✅ Accept AdCP-compliant input (only spec fields required)
- ✅ Store internal metadata (principal_id, timestamps, status)
- ✅ Return AdCP-compliant responses (internal fields filtered)
- ✅ Convert assets to adapter formats (using declarative format type detection)

Internal fields are **optional on input**, **added during processing**, and **excluded from output**. This architecture allows the sales agent to accept pure AdCP CreativeAsset objects while maintaining rich internal state for workflow management.
