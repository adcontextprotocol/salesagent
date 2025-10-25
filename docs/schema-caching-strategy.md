# AdCP Schema Caching Strategy

## Problem

The original 24-hour time-based cache was inappropriate for a rapidly evolving specification:

```python
# ❌ OLD APPROACH - Time-based caching
if datetime.now() - file_mtime > timedelta(hours=24):
    download_fresh_schema()
else:
    use_cached_schema()
```

**Issues:**
1. **Stale schemas persist** - Assumes if cached yesterday, it's still valid today
2. **No change detection** - Can't detect spec updates within 24-hour window
3. **Unnecessary downloads** - Re-downloads unchanged schemas after 24 hours
4. **Rapid evolution blind** - AdCP spec can change multiple times per day during active development

## Solution: ETag-Based Caching

Implemented HTTP conditional GET with ETag headers for efficient change detection:

```python
# ✅ NEW APPROACH - ETag-based caching
headers = {}
if cached_etag:
    headers["If-None-Match"] = cached_etag

response = await http_client.get(schema_url, headers=headers)

if response.status_code == 304:
    # Server says "Not Modified" - use cache
    return cached_schema
else:
    # Server has new version - download and cache
    save_to_cache(response.json(), response.headers["etag"])
```

### How It Works

1. **First Request**: Downloads schema, saves both content and ETag
   ```
   GET /schemas/v1/media-buy/create-media-buy-request.json
   → 200 OK
   → ETag: "68edd34b-415c"
   → Save to cache with metadata
   ```

2. **Subsequent Requests**: Sends conditional GET with ETag
   ```
   GET /schemas/v1/media-buy/create-media-buy-request.json
   If-None-Match: "68edd34b-415c"
   → 304 Not Modified (use cache)
   ```

3. **When Schema Changes**: Server returns new version
   ```
   GET /schemas/v1/media-buy/create-media-buy-request.json
   If-None-Match: "68edd34b-415c"
   → 200 OK (changed!)
   → ETag: "92fe3c7a-523d"
   → Download new version and update cache
   ```

## Benefits

### ✅ Always Fresh
- **Detects changes immediately** - No waiting for 24-hour cache expiry
- **Validates every request** - Checks with server on every test run
- **Perfect for rapid development** - Catches spec updates within seconds

### ✅ Bandwidth Efficient
- **Minimal overhead** - Conditional GET adds ~50 bytes to request
- **304 responses are tiny** - Server just says "not modified", no body
- **Only downloads when changed** - Unchanged schemas use cache

### ✅ Resilient
- **Graceful degradation** - Falls back to cache if server unavailable
- **Works offline** - Offline mode bypasses ETag checks entirely
- **Never breaks tests** - Cache serves as backup when network fails

## Cache Structure

### File Organization

```
schemas/v1/
├── index.json                    # Schema registry
├── index.json.meta              # ETag metadata for index
├── _schemas_v1_core_package_json.json       # Schema content
├── _schemas_v1_core_package_json.json.meta  # ETag metadata
└── ...
```

### Metadata Format

Each `.meta` file stores HTTP cache headers:

```json
{
  "etag": "W/\"68edd34b-415c\"",
  "last-modified": "Tue, 14 Oct 2025 04:36:27 GMT",
  "downloaded_at": "2025-10-14T00:43:25.613705",
  "schema_ref": "/schemas/v1/core/package.json"
}
```

## Implementation Details

### AdCPSchemaValidator Changes

#### 1. Metadata Management
```python
def _get_cache_metadata_path(self, cache_path: Path) -> Path:
    """Get path for cache metadata file (stores ETag, last-modified, etc)."""
    return cache_path.with_suffix(cache_path.suffix + ".meta")
```

#### 2. Online Mode Always Revalidates
```python
def _is_cache_valid(self, cache_path: Path, max_age_hours: int = 24) -> bool:
    """
    DEPRECATED time-based approach.
    Returns False in online mode (always revalidate with ETag).
    Returns True in offline mode (use any cache available).
    """
    return self.offline_mode and cache_path.exists()
```

#### 3. Conditional GET Implementation
```python
async def _download_schema(self, schema_ref: str) -> dict[str, Any]:
    # Load cached ETag
    cached_etag = load_etag_from_meta(schema_ref)

    # Send conditional GET
    headers = {"If-None-Match": cached_etag} if cached_etag else {}
    response = await http_client.get(schema_url, headers=headers)

    # Handle 304 Not Modified
    if response.status_code == 304:
        return load_from_cache(schema_ref)

    # Save new version with ETag
    save_to_cache(response.json(), response.headers["etag"])
```

### Refresh Script Updates

The `scripts/refresh_adcp_schemas.py` now handles metadata files:

```python
# Clean up both .json and .meta files
cached_files = list(cache_dir.glob("*.json"))
meta_files = list(cache_dir.glob("*.meta"))

for file in cached_files + meta_files:
    file.unlink()  # Delete everything for clean slate
```

## Usage Patterns

### Automatic Revalidation (Default)
```python
# Every test run checks for schema updates
async with AdCPSchemaValidator() as validator:
    schema = await validator.get_schema("/schemas/v1/media-buy/package.json")
    # Automatically sends conditional GET with ETag
    # Uses 304 cache or downloads new version
```

### Offline Mode
```python
# Use cached schemas only, no network requests
validator = AdCPSchemaValidator(offline_mode=True)
schema = await validator.get_schema("/schemas/v1/media-buy/package.json")
# Uses cache, raises error if cache missing
```

### Force Refresh
```bash
# Delete all cached schemas and metadata
python scripts/refresh_adcp_schemas.py

# Next test run will download fresh schemas with new ETags
pytest tests/e2e/
```

## Performance Impact

### Network Overhead
- **Conditional GET**: ~50 bytes extra per request (ETag header)
- **304 Response**: ~150 bytes (headers only, no body)
- **Full Download**: Only when schema actually changed

### Typical Test Run
```
├── index.json:                 304 Not Modified (0.05s)
├── create-media-buy-request:   304 Not Modified (0.03s)
├── package.json:               304 Not Modified (0.03s)
├── product.json:               200 OK (0.12s) ← Schema changed!
└── targeting.json:             304 Not Modified (0.03s)

Total: 5 schemas checked, 1 downloaded, 4 cached (0.26s)
```

### Comparison

| Approach | Check Frequency | Detects Changes | Bandwidth | Implementation |
|----------|----------------|-----------------|-----------|----------------|
| **Time-based (old)** | Every 24 hours | ❌ Delayed | High (full downloads) | Simple |
| **ETag-based (new)** | Every request | ✅ Immediate | Low (304 responses) | Moderate |
| **No cache** | N/A | ✅ Immediate | Very High | Simplest |
| **Static** | Never | ❌ Never | None | Fragile |

## Migration Guide

### For Developers

No code changes required! The validator automatically uses ETag caching:

```python
# This code works exactly the same
async with AdCPSchemaValidator() as validator:
    await validator.validate_response("get-products", response_data)
# But now it uses ETag-based caching internally
```

### For CI/CD

Consider running periodic refreshes to keep cache fresh:

```yaml
# GitHub Actions example
- name: Refresh AdCP schemas weekly
  if: github.event.schedule == '0 0 * * 0'  # Sunday midnight
  run: python scripts/refresh_adcp_schemas.py
```

### For Local Development

The ETag cache "just works":
- First run downloads schemas
- Subsequent runs use 304 caching
- Updates detected automatically
- No manual intervention needed

## Troubleshooting

### Schema seems outdated
```bash
# Force refresh (deletes cache and re-downloads)
python scripts/refresh_adcp_schemas.py
```

### Network issues during tests
```bash
# Use offline mode to skip ETag checks
pytest tests/e2e/ --offline-schemas
```

### Cache inconsistencies
```bash
# Check metadata files
ls -la schemas/v1/*.meta

# View ETag for specific schema
cat schemas/v1/index.json.meta
```

### Debugging ETag behavior
```python
# Enable HTTP logging to see 304 responses
import logging
logging.basicConfig(level=logging.DEBUG)
httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.DEBUG)
```

## Future Enhancements

### Potential Improvements
1. **Version pinning** - Lock to specific AdCP version for stability
2. **Checksum verification** - Validate downloaded schemas haven't been corrupted
3. **Diff reporting** - Show what changed when schema updates
4. **Auto-migration** - Detect breaking changes and suggest code updates

### Not Recommended
- ❌ **Longer cache TTL** - Defeats the purpose of change detection
- ❌ **Skip validation** - Risks using stale schemas
- ❌ **Manual cache management** - ETag automation is better

## Key Takeaways

1. **ETag caching is the correct solution** for rapidly evolving specs
2. **Time-based caching is inappropriate** when changes are frequent
3. **Always revalidate** is cheap with conditional GET
4. **Cache serves as backup** when network unavailable
5. **Metadata files are essential** for proper ETag support

This approach gives us the best of both worlds:
- ✅ Always fresh (detects changes immediately)
- ✅ Bandwidth efficient (only downloads when changed)
- ✅ Resilient (falls back to cache on errors)
- ✅ Zero maintenance (automatic in online mode)
