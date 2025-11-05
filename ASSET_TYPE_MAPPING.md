# AdCP v1 Asset Type Mappings for Ad Server Adapters

## Asset Type Reference (from AdCP v1 spec)

### 1. **Image Asset** (`image-asset.json`)
- **Required**: `url`
- **Optional**: `width`, `height`, `format`, `alt_text`
- **Use case**: Static image creatives (banners, display ads)

### 2. **Video Asset** (`video-asset.json`)
- **Required**: `url`
- **Optional**: `width`, `height`, `duration_ms`, `format`, `bitrate_kbps`
- **Use case**: Hosted video creatives (MP4, WebM)

### 3. **HTML Asset** (`html-asset.json`)
- **Required**: `content`
- **Optional**: `version`
- **Use case**: HTML5 banner ads, rich media

### 4. **JavaScript Asset** (`javascript-asset.json`)
- **Required**: `content`
- **Optional**: `module_type` (esm, commonjs, script)
- **Use case**: JavaScript-based ads, interactive creatives

### 5. **VAST Asset** (`vast-asset.json`)
- **Required**: `url` XOR `content` (exactly one)
- **Optional**: `vast_version`, `vpaid_enabled`, `duration_ms`, `tracking_events`
- **Use case**: Third-party video ad serving

### 6. **URL Asset** (`url-asset.json`)
- **Required**: `url`
- **Optional**: `url_type` (clickthrough, tracker_pixel, tracker_script), `description`
- **Use cases**:
  - `clickthrough`: Landing page URL (where user goes on click)
  - `tracker_pixel`: Impression/event tracking pixel
  - `tracker_script`: Measurement SDK (OMID, verification)

## Conversion Logic for Ad Server Adapters

### GAM/Google Ad Manager

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
  assets[*].url_type="clickthrough" → delivery_settings.tracking_urls.click
```

### Asset Role Naming Conventions

**Common roles** (priority order for primary asset detection):
1. `banner_image`, `image` - Primary image asset
2. `video`, `video_file` - Primary video asset
3. `main`, `creative`, `content` - Generic primary asset
4. `html_content`, `javascript_code` - Code assets
5. `vast_tag`, `vast` - VAST third-party tags
6. `click_url`, `clickthrough` - Landing page URL
7. `impression_tracker`, `tracker_*` - Tracking pixels

### Important Notes

1. **Duration field**: AdCP uses `duration_ms` (milliseconds), GAM uses seconds
2. **VAST oneOf**: VAST must have EITHER url OR content, never both
3. **URL type detection**: Use `url_type` field to distinguish clickthrough from trackers
4. **Multiple trackers**: Multiple impression trackers should be collected into array
5. **No asset_type field**: AdCP doesn't have top-level asset_type - detect from asset schema
