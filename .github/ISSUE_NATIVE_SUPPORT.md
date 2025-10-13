# Add GAM Native Ad Format Support

## Problem Statement

Currently, native ad formats (indicated by 1×1 size in GAM) are not properly supported. We need to:

1. Discover native style requirements from GAM API
2. Map native requirements to AdCP native formats
3. Validate native creative submissions against requirements
4. Handle native ad serving through GAM

## Current State

**What Works:**
- Standard IAB sizes (300×250, 728×90, etc.) auto-discovered from creative agents
- Dynamic format lookup from creative agents
- Format filtering by dimensions

**What's Missing:**
- No native format support
- 1×1 ad units are not handled
- No native style discovery from GAM API
- No native creative validation

## Proposed Solution

### 1. GAM Native Discovery (During Inventory Sync)

Use GAM API to discover native requirements:

```python
def discover_native_requirements(ad_unit_id: str) -> dict:
    """Discover native requirements from GAM API."""

    # Ad Unit → Native Style → Creative Template → Required Variables

    ad_unit = gam_inventory_service.getAdUnit(ad_unit_id)

    if not ad_unit.nativeAdSettings:
        return None

    # Get native styles for this ad unit
    native_style_ids = ad_unit.nativeAdSettings.nativeStyleIds

    requirements = {}
    for style_id in native_style_ids:
        # Get native style
        native_style = native_style_service.getNativeStyle(style_id)

        # Get creative template
        template = creative_template_service.getCreativeTemplate(
            native_style.creativeTemplateId
        )

        # Extract required variables
        required_vars = [
            {
                'name': var.uniqueName,
                'label': var.label,
                'type': var.type,  # STRING, URL, IMAGE, etc.
                'required': var.isRequired,
                'description': var.description
            }
            for var in template.variables
            if var.isRequired
        ]

        requirements[style_id] = {
            'style_name': native_style.name,
            'template_name': template.name,
            'required_variables': required_vars
        }

    return requirements
```

### 2. Smart Native Format Mapping

Map GAM native requirements to AdCP native formats:

```python
def suggest_native_formats(gam_native_requirements: dict) -> list[str]:
    """Suggest AdCP native formats based on GAM requirements."""

    required_vars = {req['name'] for req in gam_native_requirements['required_variables']}

    suggestions = []

    # Image-based native
    if 'image' in required_vars or 'mainImage' in required_vars:
        if 'video' in required_vars or 'videoUrl' in required_vars:
            suggestions.append('native_in_feed_video')
        else:
            suggestions.append('native_in_feed_image')

    # Content recommendation
    if 'headline' in required_vars and 'description' in required_vars:
        suggestions.append('native_content_recommendation')

    return suggestions or [
        'native_in_feed_image',
        'native_in_feed_video',
        'native_content_recommendation'
    ]
```

### 3. Database Schema

Store native requirements (not format lists):

```sql
-- Add to gam_inventory table
ALTER TABLE gam_inventory
ADD COLUMN native_requirements JSONB;

-- Example data:
{
  "style_id": "12345",
  "style_name": "In-Feed Native Style",
  "template_name": "Standard Native Template",
  "required_variables": [
    {"name": "headline", "type": "STRING", "required": true},
    {"name": "image", "type": "IMAGE", "required": true, "size": "1200x627"},
    {"name": "description", "type": "STRING", "required": false},
    {"name": "clickThroughUrl", "type": "URL", "required": true}
  ]
}
```

### 4. Product Creation UI

When selecting ad units with native:

```
Select Ad Units for Product

☑ Homepage / Header Banner (728×90)
    ✓ Standard display format (auto-detected)

☑ Homepage / Article Feed (1×1 - Native)
    Native Requirements from GAM:
    • headline (required)
    • image (required, 1200×627)
    • description (optional)
    • clickThroughUrl (required)

    Suggested Formats:
    ☑ native_in_feed_image  ✓ Matches requirements
    ☐ native_in_feed_video  (adds video support)
    ☐ native_content_recommendation

[Create Product]
```

### 5. Creative Validation

Validate native creative submissions:

```python
def validate_native_creative(creative: dict, ad_unit_id: str) -> ValidationResult:
    """Validate native creative against GAM requirements."""

    # Get native requirements from inventory
    ad_unit = get_ad_unit(ad_unit_id)
    if not ad_unit.native_requirements:
        return ValidationResult(valid=False, error="Not a native ad unit")

    requirements = ad_unit.native_requirements

    # Check required variables
    missing = []
    for req in requirements['required_variables']:
        if req['required'] and req['name'] not in creative['assets']:
            missing.append(req['label'])

    if missing:
        return ValidationResult(
            valid=False,
            error=f"Missing required fields: {', '.join(missing)}"
        )

    return ValidationResult(valid=True)
```

## Implementation Phases

### Phase 1: Discovery (2 hours)
- [ ] Add GAM API calls for native style discovery
- [ ] Store native requirements in `gam_inventory.native_requirements`
- [ ] Update inventory sync to discover native styles

### Phase 2: Format Suggestion (1 hour)
- [ ] Build `suggest_native_formats()` function
- [ ] Map GAM variables to AdCP native format types
- [ ] Display suggestions in product creation UI

### Phase 3: UI/UX (2 hours)
- [ ] Show native requirements in ad unit selection
- [ ] Allow user to select which native formats to support
- [ ] Display native style details (template name, variables)

### Phase 4: Validation (1 hour)
- [ ] Validate native creatives against GAM requirements
- [ ] Show clear error messages for missing variables
- [ ] Prevent incompatible native creatives

### Phase 5: Testing (1 hour)
- [ ] Test with real GAM native ad units
- [ ] Verify native creative submission
- [ ] Test native ad delivery

## Technical Details

### GAM API Services Needed:
- `InventoryService` - Get ad units with native settings
- `NativeStyleService` - Get native style definitions
- `CreativeTemplateService` - Get required variables

### AdCP Native Formats:
- `native_in_feed_image` - Static native ads in content feed
- `native_in_feed_video` - Video native ads in content feed
- `native_content_recommendation` - Sidebar/widget native ads

### Key Mapping:
```
GAM Native Variables → AdCP Format Type
====================================
headline + image → native_in_feed_image
headline + video → native_in_feed_video
headline + description → native_content_recommendation
```

## Benefits

1. **Accurate Mapping** - Uses GAM's own requirements to suggest formats
2. **Validation** - Ensures creatives meet native requirements
3. **Flexibility** - Supports multiple native formats per ad unit
4. **No Hardcoding** - Discovers requirements dynamically from GAM

## Alternatives Considered

### ❌ Hardcode 1×1 = Native
**Problem:** Doesn't tell us WHICH native format or what variables are needed

### ❌ Manual Mapping Table
**Problem:** Becomes outdated when GAM native styles change

### ✅ API-Driven Discovery (Chosen)
**Benefit:** Always accurate, no maintenance needed

## Related Issues

- Dynamic format lookup from creative agents (#XXX)
- Format discovery UX improvements (#XXX)

## References

- GAM Native Styles API: https://developers.google.com/ad-manager/api/reference/v202311/NativeStyleService
- GAM Creative Templates: https://developers.google.com/ad-manager/api/reference/v202311/CreativeTemplateService
- AdCP Native Format Spec: https://adcontextprotocol.org/schemas/v1/

## Questions to Resolve

1. Should we support multiple native styles per ad unit?
2. How do we handle custom GAM native variables?
3. Should we validate native creative dimensions?
4. Do we need to map GAM native macro names to AdCP field names?

## Acceptance Criteria

- [ ] GAM inventory sync discovers native requirements
- [ ] Product creation suggests native formats based on requirements
- [ ] Native creative validation works
- [ ] Clear error messages for incompatible native formats
- [ ] Documentation for native format mapping
- [ ] E2E test with real GAM native ad unit

## Estimated Effort

**Total: 7-8 hours**
- Discovery: 2 hours
- Format suggestion: 1 hour
- UI/UX: 2 hours
- Validation: 1 hour
- Testing: 1 hour
- Documentation: 1 hour
