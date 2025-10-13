# Validator Analysis: Which Can Be Fixed in Schema?

## Summary

After analyzing all 16 custom validators, here's what can be moved to JSON Schema:

**✅ Can Move to Schema (6 validators):**
1. BrandManifest.validate_required_fields - `oneOf` constraint
2. GetProductsRequest.validate_brand_or_offering - `oneOf` constraint (✅ DONE)
3. AdCPPackageUpdate.validate_oneOf_constraint - `oneOf` constraint
4. UpdateMediaBuyRequest.validate_oneOf_constraint - `oneOf` constraint
5. PricingOption.validate_pricing_option - Conditional `required` fields
6. Creative.validate_creative_fields - Mutual exclusivity (`oneOf`)

**❌ Must Stay in Code (9 validators):**
- 5x validate_timezone_aware - Runtime Python check
- 2x Backward compatibility transforms
- 2x Data normalization transforms

**⚠️ Borderline (1 validator):**
- Product.validate_pricing_fields - Can be done but complex

---

## Detailed Analysis

### ✅ CAN MOVE TO SCHEMA

#### 1. BrandManifest.validate_required_fields [Line 2263]

**Current Python:**
```python
@model_validator(mode="after")
def validate_required_fields(self) -> "BrandManifest":
    if not self.url and not self.name:
        raise ValueError("BrandManifest requires at least one of: url, name")
    return self
```

**JSON Schema Fix:**
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "/schemas/v1/core/brand-manifest.json",
  "title": "Brand Manifest",
  "type": "object",
  "properties": {
    "url": {...},
    "name": {...}
  },
  "oneOf": [
    {"required": ["url"]},
    {"required": ["name"]}
  ]
}
```

**Why this works:** Standard JSON Schema `oneOf` constraint

**Action:** Add `oneOf` to brand-manifest.json schema

---

#### 2. GetProductsRequest.validate_brand_or_offering [Line 1376]

**Status:** ✅ **ALREADY FIXED** - You just did this!

---

#### 3. AdCPPackageUpdate.validate_oneOf_constraint [Line 2917]

**Current Python:**
```python
@model_validator(mode="after")
def validate_oneOf_constraint(self):
    if not self.package_id and not self.buyer_ref:
        raise ValueError("Either package_id or buyer_ref must be provided")
    return self
```

**JSON Schema Fix:**
```json
{
  "oneOf": [
    {"required": ["package_id"]},
    {"required": ["buyer_ref"]}
  ]
}
```

**Why this works:** Standard JSON Schema `oneOf`

**Action:** Check if this schema exists in AdCP spec, add `oneOf`

---

#### 4. UpdateMediaBuyRequest.validate_oneOf_constraint [Line 2952]

**Current Python:**
```python
@model_validator(mode="after")
def validate_oneOf_constraint(self):
    if not self.media_buy_id and not self.buyer_ref:
        raise ValueError("Either media_buy_id or buyer_ref must be provided")
    if self.media_buy_id and self.buyer_ref:
        raise ValueError("Cannot provide both")
    return self
```

**JSON Schema Fix:**
```json
{
  "oneOf": [
    {"required": ["media_buy_id"]},
    {"required": ["buyer_ref"]}
  ]
}
```

**Why this works:** Standard JSON Schema `oneOf` - even enforces mutual exclusivity!

**Action:** Add to update-media-buy-request.json schema

---

#### 5. PricingOption.validate_pricing_option [Line 150]

**Current Python:**
```python
@model_validator(mode="after")
def validate_pricing_option(self) -> "PricingOption":
    if self.is_fixed and self.rate is None:
        raise ValueError("rate is required when is_fixed=true")
    if not self.is_fixed and self.price_guidance is None:
        raise ValueError("price_guidance is required when is_fixed=false")
    return self
```

**JSON Schema Fix:**
```json
{
  "type": "object",
  "properties": {
    "is_fixed": {"type": "boolean"},
    "rate": {"type": "number"},
    "price_guidance": {"type": "object"}
  },
  "oneOf": [
    {
      "properties": {"is_fixed": {"const": true}},
      "required": ["rate"]
    },
    {
      "properties": {"is_fixed": {"const": false}},
      "required": ["price_guidance"]
    }
  ]
}
```

**Why this works:** Conditional requirements based on field value

**Action:** Add to pricing-option schema (need to check if it exists)

---

#### 6. Creative.validate_creative_fields [Line 1768]

**Current Python:**
```python
@model_validator(mode="after")
def validate_creative_fields(self) -> "Creative":
    has_media = bool(self.media_url or (self.url and not self._is_html_snippet(self.url)))
    has_snippet = bool(self.snippet)

    if has_media and has_snippet:
        raise ValueError("Creative cannot have both media content and snippet")

    if self.snippet and not self.snippet_type:
        raise ValueError("snippet_type is required when snippet is provided")

    if self.snippet_type and not self.snippet:
        raise ValueError("snippet is required when snippet_type is provided")

    return self
```

**JSON Schema Fix:**
```json
{
  "type": "object",
  "properties": {
    "media_url": {"type": "string"},
    "url": {"type": "string"},
    "snippet": {"type": "string"},
    "snippet_type": {"enum": ["html", "javascript"]}
  },
  "oneOf": [
    {
      "properties": {
        "media_url": {"type": "string"},
        "snippet": {"not": {}}
      }
    },
    {
      "required": ["snippet", "snippet_type"],
      "properties": {
        "media_url": {"not": {}},
        "url": {"not": {}}
      }
    }
  ]
}
```

**Why this might not work:** The `_is_html_snippet()` method call makes this complex

**Action:** **REVIEW** - Might be too complex for pure schema

---

###❌ MUST STAY IN CODE

#### 7-11. *.validate_timezone_aware (5 instances)

**Why:** JSON Schema can't validate timezone presence in datetime strings
- Python-specific runtime check
- Validates tzinfo is not None

**Keep in code:** ✅ YES

---

#### 12. BrandManifestRef.parse_manifest_ref [Line 2284]

**Why:** This transforms data (string → object)
- Not validation, but normalization
- Modifies input

**Keep in code:** ✅ YES

---

#### 13. CreateMediaBuyRequest.handle_legacy_format [Line 2437]

**Why:** Backward compatibility transformation
- Converts promoted_offering → brand_manifest
- Modifies input for legacy clients

**Keep in code:** ✅ YES (already fixed!)

---

#### 14. PropertyTagMetadata.normalize_tags [Line 3505]

**Why:** Data normalization/transformation

**Keep in code:** ✅ YES

---

### ⚠️ BORDERLINE

#### 15. Product.validate_pricing_fields [Line 1118]

**Current Python:**
```python
@model_validator(mode="after")
def validate_pricing_fields(self) -> "Product":
    has_pricing_options = self.pricing_options is not None and len(self.pricing_options) > 0
    has_legacy_pricing = self.is_fixed_price is not None

    if not has_pricing_options and not has_legacy_pricing:
        raise ValueError("Product must have either pricing_options or legacy pricing fields")

    return self
```

**JSON Schema Fix (Possible but Complex):**
```json
{
  "oneOf": [
    {
      "required": ["pricing_options"],
      "properties": {
        "pricing_options": {
          "type": "array",
          "minItems": 1
        }
      }
    },
    {
      "required": ["is_fixed_price"]
    }
  ]
}
```

**Why borderline:** Works but represents backward compat, might be clearer in code

**Recommendation:** **CAN MOVE** but consider keeping for clarity

---

## Action Plan

### Immediate (Easy Wins)

1. **Add oneOf to brand-manifest.json**
   ```json
   "oneOf": [{"required": ["url"]}, {"required": ["name"]}]
   ```

2. **Add oneOf to update-media-buy-request.json**
   ```json
   "oneOf": [{"required": ["media_buy_id"]}, {"required": ["buyer_ref"]}]
   ```

3. **Check if these schemas exist in AdCP:**
   - pricing-option.json (for PricingOption)
   - package-update.json (for AdCPPackageUpdate)

### Next Steps

1. **File PR with AdCP to add missing oneOf constraints**
2. **Regenerate Pydantic models**
3. **Remove Python validators that are now in schema**
4. **Test thoroughly**

---

## Benefits

✅ **6 validators → JSON Schema** (5 easy + 1 complex)
✅ **9 validators stay in code** (legitimately need Python)
✅ **Net result:** ~40% reduction in custom validators
✅ **Spec compliance:** Validation rules documented in schema
✅ **Cross-platform:** Works for TypeScript too!

---

## Files to Update

### AdCP JSON Schemas (propose changes)
- `/schemas/v1/core/brand-manifest.json` - Add oneOf
- `/schemas/v1/media-buy/update-media-buy-request.json` - Add oneOf
- `/schemas/v1/core/pricing-option.json` - Add conditional required (if exists)
- Check if package-update schema exists

### After Schema Updates
1. Run `python scripts/generate_schemas.py`
2. Remove redundant Python validators
3. Update tests

---

## Summary Table

| Validator | Move to Schema? | Complexity | Action |
|-----------|----------------|------------|--------|
| BrandManifest.validate_required_fields | ✅ YES | Easy | Add oneOf |
| GetProductsRequest.validate_brand_or_offering | ✅ DONE | Easy | ✅ Complete |
| AdCPPackageUpdate.validate_oneOf_constraint | ✅ YES | Easy | Add oneOf |
| UpdateMediaBuyRequest.validate_oneOf_constraint | ✅ YES | Easy | Add oneOf |
| PricingOption.validate_pricing_option | ✅ YES | Medium | Add conditional |
| Creative.validate_creative_fields | ⚠️ MAYBE | Hard | Review |
| Product.validate_pricing_fields | ⚠️ MAYBE | Medium | Optional |
| validate_timezone_aware (5x) | ❌ NO | N/A | Keep |
| Transforms/Compat (4x) | ❌ NO | N/A | Keep |

**Total Moveable: 4-6 validators (depending on complexity tolerance)**
**Must Keep: 9 validators**
**Reduction: ~40-50%**
