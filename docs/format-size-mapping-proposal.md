# GAM Size → AdCP Format Mapping System

## Problem Statement

GAM ad units/placements specify creative sizes (300x250, 728x90, 1x1), but AdCP uses semantic format IDs (display_300x250_image, native_in_feed_video). There's currently no mapping between them.

**Critical Issue:** A placement with size 1x1 indicates native, but doesn't tell us WHICH native format to use.

## Proposed Solution

### 1. Size-to-Format Mapping Table

Create a database table: `format_size_mappings`

```sql
CREATE TABLE format_size_mappings (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(50) REFERENCES tenants(tenant_id),

    -- GAM side
    size_width INTEGER NOT NULL,
    size_height INTEGER NOT NULL,

    -- AdCP side
    format_id VARCHAR(100) NOT NULL,

    -- Metadata
    priority INTEGER DEFAULT 10,  -- Lower = preferred
    is_default BOOLEAN DEFAULT FALSE,
    notes TEXT,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(tenant_id, size_width, size_height, format_id)
);

CREATE INDEX idx_format_size_mappings_tenant_size
    ON format_size_mappings(tenant_id, size_width, size_height);
```

### 2. Default Mappings (Seeded on Tenant Creation)

```python
DEFAULT_SIZE_MAPPINGS = {
    # Display - Standard IAB Sizes
    (300, 250): ["display_300x250_image", "display_300x250_generative"],
    (728, 90): ["display_728x90_image", "display_728x90_generative"],
    (160, 600): ["display_160x600_image"],
    (300, 600): ["display_300x600_image"],
    (320, 50): ["display_320x50_image"],
    (970, 250): ["display_970x250_image"],

    # Native - Special Size Indicators
    (1, 1): [
        "native_in_feed_image",
        "native_in_feed_video",
        "native_content_recommendation"
    ],
    (2, 2): ["native_sidebar_image"],

    # Video - Companion Sizes
    (300, 250): ["video_300x250_instream"],  # Also display
    (640, 480): ["video_640x480_instream"],
}
```

### 3. UI for Managing Mappings

**Admin UI → Tenant Settings → Format Mappings**

```
GAM Size Mappings

┌─────────────────────────────────────────────────────────────┐
│ GAM Size    │ Mapped Formats              │ Priority │      │
├─────────────┼─────────────────────────────┼──────────┼──────┤
│ 300×250     │ ✓ display_300x250_image     │ 1        │ Edit │
│             │ ✓ display_300x250_generative│ 2        │      │
│             │ ✓ video_300x250_instream    │ 3        │      │
├─────────────┼─────────────────────────────┼──────────┼──────┤
│ 1×1 (Native)│ ✓ native_in_feed_image      │ 1        │ Edit │
│             │ ✓ native_in_feed_video      │ 2        │      │
│             │   native_content_rec        │ 3        │ Add  │
└─────────────┴─────────────────────────────┴──────────┴──────┘

[+ Add Size Mapping]
```

### 4. Product Configuration Flow

**When creating a product:**

1. User selects GAM ad units/placements
2. System extracts unique sizes from selected inventory
3. For each size, show mapped formats:

```
Selected Inventory Sizes: 300×250, 728×90, 1×1

Choose formats for each size:

300×250 (Display - Medium Rectangle)
☑ display_300x250_image (Standard)
☑ display_300x250_generative (AI-Generated)
☐ video_300x250_instream (Video Companion)

728×90 (Display - Leaderboard)
☑ display_728x90_image (Standard)

1×1 (Native)
☑ native_in_feed_image (In-Feed Static)
☑ native_in_feed_video (In-Feed Video)
☐ native_content_recommendation (Sidebar/Widget)
```

### 5. Runtime Format Selection

**When a media buy comes in:**

```python
def get_compatible_formats(ad_unit_sizes: list[tuple[int, int]],
                          product: Product) -> list[str]:
    """Get formats compatible with ad unit sizes."""
    compatible = []

    for width, height in ad_unit_sizes:
        # Get mapped formats for this size
        mappings = db.query(FormatSizeMapping).filter_by(
            tenant_id=product.tenant_id,
            size_width=width,
            size_height=height
        ).order_by(FormatSizeMapping.priority).all()

        # Filter to only formats in product
        for mapping in mappings:
            if mapping.format_id in product.formats:
                compatible.append(mapping.format_id)

    return compatible
```

### 6. Smart Format Discovery

**UI Enhancement: "Discover Formats from Inventory"**

When user clicks "Select Ad Units":

```python
def suggest_formats_for_inventory(ad_unit_ids: list[str]) -> dict:
    """Analyze inventory and suggest formats."""

    # 1. Get all sizes from selected ad units
    sizes = get_ad_unit_sizes(ad_unit_ids)

    # 2. Get mapped formats for each size
    format_suggestions = {}
    for width, height in sizes:
        formats = get_mapped_formats(width, height)
        format_suggestions[f"{width}x{height}"] = {
            "required": formats[:1],  # Top priority
            "recommended": formats[1:3],  # Next 2
            "optional": formats[3:],  # Rest
        }

    return format_suggestions
```

**UI Display:**

```
Inventory Analysis

Based on selected ad units, we recommend:

Required Formats (must support):
• display_300x250_image (300×250 - 15 ad units)
• display_728x90_image (728×90 - 8 ad units)
• native_in_feed_image (1×1 - 5 ad units)

Recommended (expand reach):
• display_300x250_generative (300×250 AI variant)
• native_in_feed_video (1×1 video variant)

Optional:
• video_300x250_instream (companion ads)
```

## Implementation Priority

1. **Phase 1: Data Model** (30 min)
   - Create `format_size_mappings` table
   - Migration with default mappings
   - SQLAlchemy model

2. **Phase 2: Format Discovery** (1 hour)
   - Analyze inventory sizes
   - Suggest compatible formats
   - Display in product creation flow

3. **Phase 3: Management UI** (2 hours)
   - View mappings page
   - Edit/add mappings
   - Bulk import

4. **Phase 4: Smart Matching** (1 hour)
   - Runtime format compatibility checks
   - Media buy validation
   - Warning when no compatible formats

## Benefits

1. **Solves Native Problem**: 1x1 → explicitly maps to specific native formats
2. **Multi-Format Support**: 300×250 can map to display, video, generative variants
3. **Tenant Control**: Each tenant can customize mappings for their inventory
4. **Discovery**: Auto-suggest formats based on selected inventory
5. **Validation**: Catch incompatible format selections early

## Alternative Considered: IAB Standards

IAB has standard size → placement type mappings, but:
- Doesn't cover semantic format IDs
- Doesn't handle generative/AI formats
- Doesn't allow tenant customization
- Too rigid for modern ad tech

Our approach: Use IAB sizes but map to flexible AdCP format IDs.

## Questions for Discussion

1. Should we allow multiple formats per size (YES - different types)?
2. Should we auto-populate based on IAB standards (YES - defaults)?
3. Should we validate media buys against mappings (YES - with warnings)?
4. How do we handle custom sizes not in IAB (tenant-specific mappings)?
