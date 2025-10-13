# Creative Agent Format Requirements

## Executive Summary

The AdCP Sales Agent reference implementation requires **37 creative formats** to support common advertising use cases. The creative agent currently provides **11 formats**, leaving a gap of **26 formats**.

This document outlines the missing formats needed for the creative agent to support real-world advertising inventory.

---

## Current State

### ✅ Formats Creative Agent Already Provides (11)

| Format ID | Type | Description |
|-----------|------|-------------|
| `audio_standard_30s` | Audio | 30-second audio ad |
| `display_300x250_html` | Display | 300x250 HTML5 creative |
| `display_300x250_image` | Display | 300x250 static image |
| `display_320x50_image` | Display | 320x50 mobile banner image |
| `display_728x90_html` | Display | 728x90 HTML5 creative |
| `display_728x90_image` | Display | 728x90 static image |
| `dooh_billboard_1920x1080` | DOOH | 1920x1080 digital billboard |
| `native_standard` | Native | Standard IAB native ad |
| `video_standard_15s` | Video | 15-second standard video |
| `video_standard_30s` | Video | 30-second standard video |
| `video_vast_30s` | Video | 30-second VAST tag |

---

## ❌ Missing Formats Needed (26)

### Priority 1: Essential IAB Standard Formats (15)

These are industry-standard formats that most ad servers and buyers expect to be available.

#### Display (7 formats)
| Format ID | Dimensions | Priority | Notes |
|-----------|------------|----------|-------|
| `display_160x600_image` | 160x600 | HIGH | Wide Skyscraper - common sidebar format |
| `display_336x280_image` | 336x280 | HIGH | Large Rectangle - high-performing size |
| `display_300x600_image` | 300x600 | HIGH | Half Page - premium placement |
| `display_970x250_image` | 970x250 | HIGH | Billboard - above-the-fold desktop |
| `display_970x90_image` | 970x90 | MEDIUM | Super Leaderboard |
| `display_320x480_image` | 320x480 | MEDIUM | Mobile Interstitial |
| `display_970x550_image` | 970x550 | LOW | Panorama |

**Note**: For each size, consider both `_image` and `_html` variants (like existing 300x250/728x90).

#### Video (5 formats)
| Format ID | Aspect Ratio | Priority | Notes |
|-----------|-------------|----------|-------|
| `video_1920x1080` | 16:9 | HIGH | Full HD - standard desktop video |
| `video_1280x720` | 16:9 | HIGH | 720p HD - bandwidth-efficient |
| `video_640x360` | 16:9 | MEDIUM | 360p - mobile/low bandwidth |
| `video_1080x1920` | 9:16 | HIGH | Vertical video - mobile stories |
| `video_1080x1080` | 1:1 | HIGH | Square video - social feeds |

#### Audio (2 formats)
| Format ID | Duration | Priority | Notes |
|-----------|----------|----------|-------|
| `audio_standard_15s` | 15s | HIGH | Standard 15-second audio spot |
| `audio_standard_60s` | 60s | MEDIUM | Standard 60-second audio spot |

**Note**: `audio_standard_30s` already exists ✅

#### Native (1 format)
| Format ID | Type | Priority | Notes |
|-----------|------|----------|-------|
| `native_content` | Content | HIGH | In-article native placement |

**Note**: `native_standard` already exists ✅

---

### Priority 2: Connected TV Formats (2)

Critical for streaming inventory - fastest-growing segment.

| Format ID | Type | Priority | Notes |
|-----------|------|----------|-------|
| `video_ctv_preroll_30s` | Video | HIGH | Pre-roll ad for CTV/streaming |
| `video_ctv_midroll_30s` | Video | MEDIUM | Mid-roll ad for CTV/streaming |

---

### Priority 3: AdCP Foundational Formats (4)

These are part of the AdCP spec and enable advanced creative experiences.

| Format ID | Type | Priority | Notes |
|-----------|------|----------|-------|
| `foundation_universal_video` | Video | HIGH | Multi-aspect-ratio video that adapts |
| `foundation_product_showcase_carousel` | Display | MEDIUM | Product carousel (3-10 products) |
| `foundation_expandable_display` | Display | MEDIUM | Expandable rich media |
| `foundation_scroll_triggered_experience` | Display | LOW | Scroll-parallax creative |

---

### Priority 4: DOOH Formats (3)

Digital Out-of-Home is growing rapidly and needs specific formats.

| Format ID | Dimensions | Priority | Notes |
|-----------|------------|----------|-------|
| `dooh_billboard_landscape` | Various | MEDIUM | Landscape orientation billboards |
| `dooh_billboard_portrait` | Various | MEDIUM | Portrait orientation billboards |
| `dooh_transit_screen` | Various | LOW | Transit/subway screens |

**Note**: `dooh_billboard_1920x1080` already exists ✅

---

### Priority 5: Rich Media Formats (2)

Enhanced interactive experiences.

| Format ID | Type | Priority | Notes |
|-----------|------|----------|-------|
| `rich_media_expandable` | Display | MEDIUM | User-initiated expandable ads |
| `rich_media_interstitial` | Display | LOW | Full-screen interstitials |

---

## Format Design Principles

When implementing these formats, follow these patterns from existing formats:

### 1. Naming Convention
```
{type}_{variant}_{detail}
```

Examples:
- `display_300x250_image` (type_size_variant)
- `video_standard_30s` (type_variant_duration)
- `audio_standard_15s` (type_variant_duration)

### 2. Required Fields per AdCP v2.4
Every format should include:
- `format_id` - Unique identifier
- `agent_url` - https://creative.adcontextprotocol.org
- `name` - Human-readable name
- `type` - One of: audio, video, display, native, dooh, rich_media, universal
- `category` - "standard" or "custom"
- `is_standard` - Boolean
- `description` - Clear description
- `iab_specification` - Link to IAB spec (if applicable)
- `accepts_3p_tags` - Boolean
- `dimensions` - String like "300x250" (if applicable)
- `supported_macros` - Array of macro names
- `requirements` - Technical requirements object
- `assets_required` - Array of asset requirements

### 3. Asset Requirements Structure
```json
{
  "asset_role": "banner_image",
  "asset_type": "image",
  "required": true,
  "width": 300,
  "height": 250,
  "max_file_size_mb": 0.2,
  "acceptable_formats": ["jpg", "png", "gif", "webp"],
  "description": "Banner image for 300x250 placement"
}
```

### 4. Supported Macros
Standard macros that should be supported across most formats:
- `MEDIA_BUY_ID`
- `CREATIVE_ID`
- `CACHEBUSTER`
- `CLICK_URL`
- `IMPRESSION_URL`
- `DEVICE_TYPE`
- `GDPR`
- `GDPR_CONSENT`
- `US_PRIVACY`
- `GPP_STRING`

Additional macros for video:
- `VIDEO_ID`
- `POD_POSITION`
- `CONTENT_GENRE`

Additional macros for DOOH:
- `SCREEN_ID`
- `VENUE_TYPE`
- `VENUE_LAT`
- `VENUE_LONG`

---

## Implementation Priority

### Phase 1 (Essential - Week 1)
**Target: 15 formats → 26 total**

1. ✅ Display sizes: 160x600, 336x280, 300x600, 970x250 (image + html variants = 8 formats)
2. ✅ Video resolutions: 1920x1080, 1280x720, 1080x1920, 1080x1080 (4 formats)
3. ✅ Audio: 15s, 60s (2 formats)
4. ✅ Native: content placement (1 format)

### Phase 2 (CTV - Week 2)
**Target: +2 formats → 28 total**

5. ✅ CTV pre-roll and mid-roll (2 formats)

### Phase 3 (Advanced - Week 3)
**Target: +9 formats → 37 total**

6. ✅ Foundational formats (4 formats)
7. ✅ DOOH variants (3 formats)
8. ✅ Rich media (2 formats)

---

## Testing Checklist

For each format implementation, verify:

- [ ] Format appears in `list_creative_formats` response
- [ ] `agent_url` points to https://creative.adcontextprotocol.org
- [ ] All required fields are present and valid
- [ ] Asset requirements are complete and accurate
- [ ] Supported macros list is comprehensive
- [ ] `preview_creative` generates valid preview
- [ ] `build_creative` validates assets correctly
- [ ] Format validates against AdCP schema

---

## Questions for AdCP Team

1. **Naming Convention**: Should we standardize on `{size}_{variant}` (e.g., `display_300x250_image`) or `{variant}_{size}` (e.g., `image_display_300x250`)?

2. **IAB Alignment**: Should all IAB standard sizes be supported, or subset based on usage data?

3. **Foundational Formats**: What's the timeline for full AdCP foundational format support?

4. **Custom Formats**: Should publishers be able to register custom formats with the creative agent, or should they run their own creative agent?

5. **Preview Generation**: For formats like carousels and expandable, what preview fidelity is expected? (static screenshot vs interactive preview)

6. **Asset Validation**: Should the creative agent provide strict validation (reject invalid assets) or lenient validation (warnings only)?

---

## Contact

For questions about these requirements:
- **Repository**: https://github.com/adcontextprotocol/adcp-sales-agent
- **Issue Tracker**: https://github.com/adcontextprotocol/adcp/issues
- **Maintainer**: Brian O'Kelley (@bokelley)

---

**Document Version**: 1.0
**Last Updated**: 2025-10-12
**Status**: Draft - Awaiting AdCP Team Review
