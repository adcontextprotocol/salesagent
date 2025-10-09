# Creative Placeholder Gap Analysis

## Problem Summary

The format extensibility system allows configuring 1x1 placeholders for GAM native templates, but the creative validation system will reject real creatives that don't match 1x1 dimensions.

## Current Flow

### 1. Line Item Creation (orders.py)
```python
# We correctly create 1x1 placeholder with template ID
if "creative_template_id" in placeholder_cfg:
    placeholder["size"] = {"width": 1, "height": 1, "isAspectRatio": False}
    placeholder["creativeTemplateId"] = placeholder_cfg["creative_template_id"]
```

✅ **Works correctly** - GAM line item created with proper 1x1 placeholder + template ID

### 2. Creative Sync (creatives.py lines 267-323)
```python
def _validate_creative_size_against_placeholders(asset, creative_placeholders):
    asset_width, asset_height = self._get_creative_dimensions(asset, None)

    # Check if dimensions match placeholder
    if asset_width == placeholder_width and asset_height == placeholder_height:
        matching_placeholders_found = True
```

❌ **FAILS** - Buyer sends 300x250 creative, but placeholder is 1x1, so `300 != 1`

### 3. GAM Creative Association (creatives.py line 624)
```python
lica_service.createLineItemCreativeAssociations([association])
```

🔲 **NEVER REACHED** - Validation fails before we get here

## Real-World Scenarios

### Scenario 1: Native Ads with Template
**Publisher Setup:**
- Product configured with format override: `creative_template_id: 12345678`
- Line item created with 1x1 placeholder + template ID

**Buyer Action:**
- Sends native creative via `sync_creatives` with actual dimensions (e.g., 1200x627 for Facebook-style native)

**Current Result:**
```
❌ Creative validation failed: Creative size 1200x627 does not match any LineItem placeholders.
   Available sizes in assigned packages: 1x1
```

**What Should Happen:**
✅ Accept the creative and associate it with the 1x1 placeholder (GAM native template will handle rendering)

### Scenario 2: Programmatic/Header Bidding
**Publisher Setup:**
- Product for programmatic inventory with 1x1 placeholders (no template ID)
- Buyer will send third-party tags that render at runtime

**Buyer Action:**
- Sends creative with `third_party_url` and dimensions 300x250

**Current Result:**
```
❌ Creative validation failed: Creative size 300x250 does not match any LineItem placeholders.
   Available sizes in assigned packages: 1x1
```

**What Should Happen:**
✅ Accept the creative - 1x1 is a wildcard for programmatic

### Scenario 3: Standard Display (No Issues)
**Publisher Setup:**
- Standard format: `display_300x250` with normal 300x250 placeholder

**Buyer Action:**
- Sends 300x250 creative

**Current Result:**
✅ Works correctly - dimensions match

## Root Cause

The validation logic in `_validate_creative_size_against_placeholders()` treats 1x1 as a literal size requirement instead of recognizing it as a special GAM pattern with different semantics:

1. **1x1 + template_id** = GAM native creative template (accepts any dimensions)
2. **1x1 without template_id** = Programmatic/third-party tag (accepts any dimensions)
3. **Normal dimensions** = Strict size match required

## Proposed Solution

### Option 1: Skip Size Validation for 1x1 Placeholders (Recommended)

Update `_validate_creative_size_against_placeholders()`:

```python
def _validate_creative_size_against_placeholders(asset, creative_placeholders):
    # ... existing dimension extraction ...

    for package_id in package_assignments:
        placeholders = creative_placeholders.get(package_id, [])
        for placeholder in placeholders:
            placeholder_size = placeholder.get("size", {})
            placeholder_width = placeholder_size.get("width", 0)
            placeholder_height = placeholder_size.get("height", 0)

            # 1x1 placeholders are wildcards (native templates or programmatic)
            if placeholder_width == 1 and placeholder_height == 1:
                matching_placeholders_found = True
                logger.info(
                    f"Creative {asset_width}x{asset_height} matches 1x1 wildcard placeholder "
                    f"(native template or programmatic)"
                )
                break

            # Standard placeholders require exact match
            if asset_width == placeholder_width and asset_height == placeholder_height:
                matching_placeholders_found = True
                break
```

**Pros:**
- Simple and correct for GAM semantics
- Handles both native templates and programmatic
- No configuration changes needed

**Cons:**
- Could accidentally accept wrong-sized creatives if 1x1 used incorrectly

### Option 2: Check for creative_template_id in Placeholder

Store template_id in placeholder metadata during line item creation, check it during validation:

```python
# In orders.py line item creation
if "creative_template_id" in placeholder_cfg:
    placeholder["size"] = {"width": 1, "height": 1}
    placeholder["creativeTemplateId"] = placeholder_cfg["creative_template_id"]
    placeholder["_is_native_template"] = True  # Metadata flag
```

```python
# In creatives.py validation
if placeholder.get("_is_native_template") or (placeholder_width == 1 and placeholder_height == 1):
    # Accept any size for native templates or 1x1 wildcards
    matching_placeholders_found = True
```

**Pros:**
- More explicit about template vs non-template 1x1
- Could add stricter validation in future

**Cons:**
- More complex
- Requires passing metadata through line item creation

### Option 3: Format-Based Validation Logic

Check the format type during validation:

```python
def _validate_creative_size_against_placeholders(asset, creative_placeholders, format_obj):
    # If format has creative_template_id, skip size validation
    if format_obj.platform_config.get("gam", {}).get("creative_placeholder", {}).get("creative_template_id"):
        return []  # No validation errors for template-based formats

    # Otherwise, strict size matching
    # ... existing validation ...
```

**Pros:**
- Most semantically correct - validation based on format configuration
- Could handle other special cases per format

**Cons:**
- Requires passing format_obj through validation pipeline
- More refactoring needed

## Recommendation

**Implement Option 1** because:
1. It's the simplest and matches GAM's actual behavior
2. 1x1 placeholders ARE wildcards in GAM - this is not a hack, it's how GAM works
3. No refactoring or data passing changes needed
4. Works for all three use cases (native templates, programmatic, standard)

## Additional Considerations

### Do Buyers Understand 1x1 Hacks?

**No, they shouldn't need to!** This is exactly why we need this fix:

- Buyer sees format: `"native_in_feed"` with requirements: `{"width": 1200, "height": 627}`
- Buyer sends creative with those dimensions
- **Internal GAM mapping** (via platform_config) uses 1x1 placeholder
- Validation should handle this translation transparently

### What About Creative IDs in create_media_buy?

Currently, `Package.creative_ids` is **not used** during line item creation. Creatives are associated later via `sync_creatives`. This is correct because:

1. **Line items need placeholders** - these define what creatives are expected
2. **Creatives come later** - buyer uploads/syncs creatives after media buy is created
3. **Association is async** - `sync_creatives` → validates → creates GAM creative → associates with line item

If buyer provides `creative_ids` in `create_media_buy` request, we should:
- ✅ Store them in the database (`Package.creative_ids`)
- ✅ Return them in responses
- ❌ **Do NOT** try to associate them during order/line item creation (creatives don't exist yet in GAM)
- ✅ Associate them when `sync_creatives` is called

### What If Creatives Are Added Later?

**Current behavior is correct:**

1. `create_media_buy` → Creates GAM order + line items with placeholders
2. Buyer creates creatives via AdCP creative endpoints
3. `sync_creatives` → Validates + uploads + associates with line items
4. Buyer can call `sync_creatives` multiple times to add/update

**No code changes needed** - this flow already works correctly (except for 1x1 validation bug).

## Implementation Plan

1. ✅ Fix `_validate_creative_size_against_placeholders()` to treat 1x1 as wildcard
2. ✅ Add logging to indicate when 1x1 wildcard matching is used
3. ✅ Add tests for 1x1 placeholder scenarios
4. ✅ Document that 1x1 is transparent to buyers (internal GAM mapping)

## Test Cases Needed

```python
def test_creative_validation_accepts_1x1_wildcard_for_native_template():
    """1x1 placeholder with template_id accepts any creative size."""
    placeholder = {"size": {"width": 1, "height": 1}, "creativeTemplateId": 12345678}
    asset = {"width": 1200, "height": 627}  # Native creative
    # Should validate successfully

def test_creative_validation_accepts_1x1_wildcard_for_programmatic():
    """1x1 placeholder without template_id accepts any creative size."""
    placeholder = {"size": {"width": 1, "height": 1}}
    asset = {"width": 300, "height": 250, "third_party_url": "..."}
    # Should validate successfully

def test_creative_validation_requires_exact_match_for_standard():
    """Non-1x1 placeholders require exact dimension match."""
    placeholder = {"size": {"width": 300, "height": 250}}
    asset = {"width": 728, "height": 90}  # Wrong size
    # Should fail validation
```
