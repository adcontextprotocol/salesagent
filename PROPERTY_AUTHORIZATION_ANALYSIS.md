# Property Authorization Analysis

## Problem Statement

The current implementation of property authorization in products has **significant misalignment** with the AdCP specification and conceptual confusion about what properties represent.

## What AdCP Spec Actually Says

### Product Schema (`/schemas/v1/core/product.json`)

```json
{
  "publisher_properties": {
    "type": "array",
    "description": "Publisher properties covered by this product. Buyers fetch actual property definitions from each publisher's adagents.json and validate agent authorization.",
    "items": {
      "type": "object",
      "properties": {
        "publisher_domain": {
          "type": "string",
          "description": "Domain where publisher's adagents.json is hosted (e.g., 'cnn.com')"
        },
        "property_ids": {
          "type": "array",
          "description": "Specific property IDs from the publisher's adagents.json. Mutually exclusive with property_tags."
        },
        "property_tags": {
          "type": "array",
          "description": "Property tags from the publisher's adagents.json. Product covers all properties with these tags. Mutually exclusive with property_ids."
        }
      },
      "required": ["publisher_domain"]
    },
    "minItems": 1
  }
}
```

### Property Schema (`/schemas/v1/core/property.json`)

A **Property** represents an advertising property that can be validated via `adagents.json`:
- **property_type**: website, mobile_app, ctv_app, dooh, podcast, radio, streaming_audio
- **name**: Human-readable name (e.g., "CNN.com", "ESPN iOS App")
- **identifiers**: Array of identifiers (domain, app_id, etc.) for validation
- **tags**: Tags for categorization (e.g., "conde_nast_network", "premium_sports")
- **publisher_domain**: Domain where adagents.json should be checked

## What Our Implementation Does (WRONG)

### Database Schema (`src/core/database/models.py:183-202`)

```python
class Product(Base):
    # Legacy fields that don't match AdCP spec
    properties: list[dict] | None  # Full Property objects
    property_tags: list[str] | None  # Tag strings

    # XOR constraint - must have one or the other
    __table_args__ = (
        CheckConstraint(
            "(properties IS NOT NULL AND property_tags IS NULL) OR
             (properties IS NULL AND property_tags IS NOT NULL)",
            name="ck_product_properties_xor"
        ),
    )
```

**Issues:**
1. ❌ Field is named `properties` instead of `publisher_properties`
2. ❌ No `publisher_domain` field (required by spec)
3. ❌ `property_tags` is a simple array, not nested under publisher_properties
4. ❌ Structure doesn't support multi-publisher products
5. ❌ XOR constraint doesn't match spec (spec allows both in different publisher_properties items)

### Product Response (`src/core/main.py:287-297`)

```python
product_data = {
    # ...
    "properties": safe_json_parse(product.properties) if product.properties else None,
    "property_tags": (
        safe_json_parse(product.property_tags)
        if product.property_tags
        else ["all_inventory"]  # Default fallback
    ),
}
```

**Issues:**
1. ❌ Returns legacy `properties` and `property_tags` fields
2. ❌ Spec expects `publisher_properties` field
3. ❌ Default to `["all_inventory"]` violates spec (requires publisher_domain)

### Admin UI (`templates/add_product.html:441-538`)

```html
<h3>Property Authorization (AdCP) *</h3>

<!-- Two modes: property tags or full properties -->
<input type="radio" name="property_mode" value="tags" checked>
<input type="radio" name="property_mode" value="full">

<!-- Tag mode -->
<input type="text" name="property_tags" value="all_inventory">

<!-- Full mode -->
<input type="checkbox" name="property_ids" value="{{ prop.id }}">
```

**Issues:**
1. ❌ UI treats this as product-level authorization
2. ❌ No `publisher_domain` field (required!)
3. ❌ Confusing explanation - says "buyers validate against their authorized properties"
4. ❌ Should be asking: "Which websites/apps/properties does this product cover?"

## Conceptual Confusion

### What Properties SHOULD Be (Per AdCP Spec)

**Properties = Publisher Inventory (Websites/Apps/Podcasts)**

A Product's `publisher_properties` answers:
> "Which publisher websites, apps, or media properties does this product provide advertising on?"

Examples:
- Product "CNN Premium Display" covers: `cnn.com`, `cnn.com/politics`, CNN iOS app
- Product "Conde Nast Network" covers: All properties tagged `conde_nast_network` (vogue.com, wired.com, etc.)
- Product "Local Radio Package" covers: Specific radio stations by call sign

**Authorization Flow:**
1. **Publisher** (sales agent): Lists properties in `publisher_properties` on Product
2. **Buyer agent**: Fetches publisher's `adagents.json` from each `publisher_domain`
3. **Buyer agent**: Validates sales agent is authorized in `adagents.json`
4. **Buyer agent**: Validates requested properties exist and match product definition

### What Our Code Thinks Properties Are (WRONG)

Our code seems to think properties are:
- Some kind of abstract "authorization tags"
- Something that needs XOR constraint (either tags OR full objects)
- Defaults to `["all_inventory"]` when not specified

This doesn't align with the spec's intent. Properties are **concrete publisher inventory** (domains, apps, etc.).

## What Should Happen

### Option 1: Fix Database Schema to Match Spec (Breaking Change)

```python
class Product(Base):
    # Remove legacy fields
    # properties: REMOVED
    # property_tags: REMOVED

    # Add spec-compliant field
    publisher_properties: list[dict] = mapped_column(JSONType, nullable=False)
    # Structure: [
    #   {
    #     "publisher_domain": "cnn.com",
    #     "property_ids": ["cnn_homepage", "cnn_politics"]  # OR
    #     "property_tags": ["premium_news"]
    #   }
    # ]
```

**Migration required:**
- Rename `properties`/`property_tags` → `publisher_properties`
- Add `publisher_domain` (derive from tenant's primary domain?)
- Restructure data to nested format

### Option 2: Map Internal Schema to AdCP Spec (Non-Breaking)

Keep database schema, but transform when returning products:

```python
def product_to_adcp_format(product):
    # Transform internal format to AdCP spec
    publisher_properties = []

    if product.property_tags:
        publisher_properties.append({
            "publisher_domain": tenant.primary_domain,  # Need to add this!
            "property_tags": product.property_tags
        })
    elif product.properties:
        # Extract publisher_domain from properties
        # Group properties by publisher_domain
        # Build proper publisher_properties structure
        pass

    return {
        "product_id": product.product_id,
        # ... other fields
        "publisher_properties": publisher_properties  # Spec-compliant!
    }
```

### Option 3: Make It Truly Optional (Recommended for GAM)

**For GAM products specifically**, properties might be derivable from inventory:

```python
# GAM Product
publisher_properties = [
    {
        "publisher_domain": tenant.primary_domain,
        "property_ids": derive_from_ad_units(product.implementation_config["targeted_ad_unit_ids"])
    }
]
```

Where `derive_from_ad_units` looks at:
- Ad unit paths (e.g., `/sports/basketball` → property "sports_section")
- Ad unit metadata (custom targeting keys)
- Placement mappings

## Recommendations

### Immediate Fix (Non-Breaking)

1. **Add `publisher_domain` to Tenant model** (if not exists)
   - This is the domain for `adagents.json` validation
   - Required for spec compliance

2. **Transform product responses** to include `publisher_properties`:
   ```python
   # In get_products response
   "publisher_properties": [
       {
           "publisher_domain": tenant.primary_domain,
           "property_tags": product.property_tags or ["all_inventory"]
       }
   ]
   ```

3. **Update UI explanation** to clarify:
   ```html
   <h3>Publisher Properties (Which sites/apps does this cover?)</h3>
   <p>Specify which websites, mobile apps, or media properties this product provides advertising on.</p>
   ```

4. **For GAM products**: Derive properties from ad units/placements
   - Map ad unit paths → property IDs
   - Use ad unit metadata → property tags
   - Show in UI: "Properties: Derived from 12 ad units (cnn.com, cnn.com/sports)"

### Long-Term Fix (Breaking Change for v2.0)

1. **Database migration**:
   - Rename fields to match spec
   - Add `publisher_domain` field
   - Restructure to nested `publisher_properties` format

2. **Remove XOR constraint** (spec doesn't require this)

3. **Admin UI redesign**:
   - "Which domains/apps does this product cover?"
   - Domain input field (required)
   - Property selection per domain
   - Tag-based selection for network packages

## Why This Matters

**Current issues:**
- ❌ Products don't include `publisher_domain` → buyers can't validate `adagents.json`
- ❌ Response format doesn't match spec → buyers see wrong schema
- ❌ UI is confusing → publishers don't understand what to enter
- ❌ GAM products don't leverage inventory → duplicate data entry

**After fix:**
- ✅ Buyers can validate authorization via `adagents.json`
- ✅ Response matches AdCP spec exactly
- ✅ UI clearly asks "which sites/apps?"
- ✅ GAM products auto-derive from inventory (less manual work)

## Questions to Resolve

1. **Should `publisher_properties` be required or optional?**
   - Spec says `minItems: 1` (required)
   - But some products might cover "any property" (programmatic marketplace)
   - Recommendation: Required, but allow wildcard like `{"publisher_domain": "*.example.com", "property_tags": ["all_inventory"]}`

2. **Where does `publisher_domain` come from?**
   - Tenant model should have primary domain
   - Products might cover multiple publisher domains (network packages)
   - Recommendation: Add `tenant.primary_domain`, allow multi-domain products

3. **Should GAM ad units map to properties automatically?**
   - Yes! Ad unit `/sports/basketball` → property_id `sports_basketball`
   - Reduces manual work, ensures consistency
   - Recommendation: Add property derivation for GAM products

4. **What about property validation during `create_media_buy`?**
   - Current code doesn't validate buyer's authorized properties against product properties
   - Should we implement this check?
   - Recommendation: Yes, add validation (but make it a warning, not error, for now)
