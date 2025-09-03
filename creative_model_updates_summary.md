# Creative Model Updates - AdCP Compliance

## Overview
Updated the Creative model to be fully compliant with the AdCP (Advertising Context Protocol) specification for creative asset responses.

## Changes Made

### ✅ Added AdCP Required Fields
- `creative_id` ✅ (already present)
- `name` ✅ (already present)
- `format` ✅ (already present, with alias support)

### ✅ Added AdCP Optional Fields
- `url` ✅ (creative content URL - already present)
- `media_url` ✅ (alternative media URL, defaults to `url`)
- `click_url` ✅ (landing page URL - already present)
- `duration` ✅ (for video/audio content)
- `width` ✅ (pixel width for video/display)
- `height` ✅ (pixel height for video/display)
- `status` ✅ (creative approval status)
- `platform_id` ✅ (platform-assigned ID)
- `review_feedback` ✅ (platform review comments)
- `compliance` ✅ (compliance review status with auto-default)
- `package_assignments` ✅ (assigned package IDs)
- `assets` ✅ (for multi-asset formats like carousels)

### ✅ Internal Field Management
Internal fields are excluded from AdCP responses but available for internal processing:
- `principal_id` (tenant isolation)
- `group_id` (creative organization)
- `created_at` / `updated_at` (timestamps)
- `has_macros` / `macro_validation` (macro processing)
- `asset_mapping` (internal asset mapping)
- `metadata` (platform-specific metadata)

### ✅ Dual Interface Support
- **`model_dump()`** - AdCP-compliant external responses (15 fields)
- **`model_dump_internal()`** - Full internal data for database/processing (23 fields)

### ✅ Backward Compatibility
Maintains compatibility with existing code via property aliases:
- `format_id` → `format`
- `content_uri` → `url`
- `click_through_url` → `click_url`

## Sample AdCP Response
```json
{
  "creative_id": "test_adcp_creative",
  "name": "AdCP Test Creative",
  "format": "video_1920x1080",
  "url": "https://example.com/video.mp4",
  "media_url": "https://example.com/video.mp4",
  "click_url": "https://example.com/landing",
  "duration": 30.0,
  "width": 1920,
  "height": 1080,
  "status": "approved",
  "platform_id": "platform_123",
  "review_feedback": "Approved for all placements",
  "compliance": {
    "status": "pending",
    "issues": []
  },
  "package_assignments": ["package_1", "package_2"],
  "assets": null
}
```

## Testing Results
- ✅ All AdCP contract tests pass (10/10)
- ✅ All creative-related unit tests pass
- ✅ Backward compatibility maintained
- ✅ Internal/external field separation working correctly

## Usage
```python
# Create creative
creative = Creative(
    creative_id='id',
    name='My Creative',
    format_id='display_300x250',  # Alias support
    content_uri='https://example.com/creative.jpg',  # Alias support
    principal_id='buyer_1',  # Internal field
    created_at=datetime.now(),  # Internal field
    updated_at=datetime.now(),  # Internal field
    width=300,
    height=250
)

# AdCP-compliant response (excludes internal fields)
adcp_response = creative.model_dump()  # 15 fields

# Full internal data (includes all fields)
internal_data = creative.model_dump_internal()  # 23 fields
```

The Creative model now fully complies with the AdCP specification while maintaining internal functionality and backward compatibility.
