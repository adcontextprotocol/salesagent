# Creative Preview Architecture

## Problem Statement

The current implementation has the sales agent responsible for rendering creative previews for all creative formats. This creates several issues:

1. **Tight Coupling**: Sales agent needs to understand rendering logic for every creative format
2. **Duplication**: Every AdCP implementation needs to rebuild preview rendering
3. **Limited Scope**: Previews can't fill in macros or show real-world rendering
4. **No Standalone Tool**: Can't validate creative manifests outside of sales agent context

## Proposed Solution

### AdCP Spec Change: Add `preview_url` to Creative Format

The Creative Format specification should include an optional `preview_url` field that provides a standalone preview tool for that format.

```json
{
  "format_id": "display_300x250",
  "name": "Display 300x250",
  "type": "display",
  "dimensions": {
    "width": 300,
    "height": 250
  },
  "preview_url": "https://adcp.org/preview?format=display_300x250&manifest={manifest_url}",
  "manifest_schema": { ... }
}
```

### Benefits

1. **Decoupling**: Sales agents don't need rendering logic
2. **Reusability**: One preview tool serves all AdCP implementations
3. **Macro Support**: Preview tool can fill in macros (click tracking, impression pixels, etc.)
4. **Validation**: Standalone tool for testing creative manifests
5. **Flexibility**: Publishers can provide custom previews for custom formats

### Implementation Phases

#### Phase 1: External Preview URLs (Immediate)

**Sales Agent Responsibility:**
- Store `preview_url` from creative format specification
- For standard AdCP formats: Use format's `preview_url`
- For custom publisher formats: Generate internal preview

**UI Changes:**
- "Preview" button opens `preview_url` in new tab/modal
- Pass creative manifest URL as query parameter
- Preview tool renders creative with filled macros

**Example Flow:**
```
1. User clicks "Preview" on creative
2. Sales agent constructs URL:
   https://adcp.org/preview?format=display_300x250&manifest=https://cdn.example.com/creative.json
3. Opens in new tab
4. Preview tool fetches manifest, renders creative, fills macros
```

#### Phase 2: AdCP Platform Preview Tool (Future)

**Standalone Preview Service:**
- Hosted at `preview.adcontextprotocol.org` or similar
- Accepts format + manifest URL
- Renders creative with filled macros
- Shows validation errors
- Provides embed code for iframes

**Features:**
- Real-time macro filling (CLICK_URL, IMP_PIXEL, etc.)
- Format specification validation
- Mobile/desktop/tablet previews
- Dark mode preview
- Accessibility checks

**API:**
```
GET /preview?format={format_id}&manifest={manifest_url}
GET /validate?format={format_id}&manifest={manifest_url}
POST /preview (body: format spec + manifest)
```

#### Phase 3: Publisher Custom Formats (Long-term)

**For Custom Publisher Formats:**
- Publisher provides `preview_url` in format definition
- Sales agent stores and uses publisher's preview URL
- Falls back to basic internal preview if not provided

**Example Custom Format:**
```json
{
  "format_id": "custom_sports_ticker",
  "name": "Sports Ticker Widget",
  "type": "custom",
  "is_standard": false,
  "preview_url": "https://publisher.com/creative-preview?format=sports_ticker",
  "manifest_schema": { ... }
}
```

### Migration Path

**Existing Code:**
- Keep internal preview rendering for custom formats without `preview_url`
- Add `preview_url` field to `CreativeFormat` model
- Update UI to prefer external preview URLs

**Database Schema:**
```sql
ALTER TABLE creative_formats ADD COLUMN preview_url TEXT;
```

**UI Logic:**
```python
if creative_format.preview_url:
    # Use external preview
    preview_link = f"{creative_format.preview_url}?manifest={creative.manifest_url}"
else:
    # Use internal preview (legacy/custom formats only)
    preview_link = url_for('creatives.preview_internal', creative_id=creative_id)
```

## Open Questions

1. **Who hosts the preview tool?**
   - AdCP Foundation?
   - Community project?
   - Multiple implementations?

2. **Preview URL format standard?**
   - Query params vs path params?
   - Manifest URL vs inline manifest?
   - Authentication for private manifests?

3. **Validation vs Preview?**
   - Separate endpoints?
   - Validation included in preview?

4. **Macro filling?**
   - Preview tool responsibility?
   - Publisher responsibility?
   - Test vs production macros?

## Next Steps

1. ✅ Document architecture (this doc)
2. ⏸️ Propose spec change to AdCP community
3. ⏸️ Build reference preview tool
4. ⏸️ Update sales agent to use external previews
5. ⏸️ Migrate standard formats to use preview URLs

## Related Files

- `src/admin/blueprints/creatives.py` - Review/preview UI
- `templates/review_creatives.html` - Preview rendering
- `src/core/database/models.py` - CreativeFormat model
- AdCP Spec: Creative Format definition

## Author

Brian O'Kelley
Date: 2025-10-08
Status: Proposed
