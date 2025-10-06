# Wonderstruck Package Name Generation Bug

## Summary

Wonderstruck is not using the `buyer_ref` field we provide in packages when generating package names, resulting in non-unique generic names like "None - 1 packages" instead of meaningful unique identifiers.

## What We're Sending (Correct)

We send the `buyer_ref` field in each package according to the AdCP spec:

```json
{
  "promoted_offering": "Acme Corp - Summer Campaign",
  "packages": [
    {
      "buyer_ref": "pkg_ref_1759759563873",  // ✅ Unique identifier we provide
      "products": ["prod_1", "prod_2"],
      "budget": {
        "total": 50000.0,
        "currency": "USD"
      }
    }
  ]
}
```

**Source Code Reference**: `/Users/brianokelley/Developer/salesagent/.conductor/dublin/src/core/schemas.py:1930`

When converting legacy format to AdCP v2.4 packages, we auto-generate `buyer_ref`:

```python
# schemas.py line 1930
"buyer_ref": f"pkg_{i}_{package_uuid}",  # Client reference for tracking
```

This creates unique buyer references like:
- `pkg_0_abc123`
- `pkg_ref_1759759563873`
- `summer_campaign_package_1`

## What They're Generating (Incorrect)

Wonderstruck generates: `"None - 1 packages"`

This indicates they're:
1. **Not reading the `buyer_ref` field** we provide
2. **Using some internal logic** that doesn't incorporate our unique identifier
3. **Creating non-unique names** when multiple packages exist

## What They Should Generate

Wonderstruck should use the `buyer_ref` we provide to create unique, meaningful names:

### Option 1: Use buyer_ref directly
```
Name: "pkg_ref_1759759563873"
```

### Option 2: Combine with promoted_offering
```
Name: "Acme Corp - Summer Campaign - pkg_ref_1759759563873"
```

### Option 3: Extract timestamp from buyer_ref
```
Name: "Package 1759759563873"
```

### Option 4: Simple numbering with context
```
Name: "Acme Corp Package 1"  // Uses promoted_offering
```

## Why This is Their Bug

### AdCP Spec Compliance

From the [AdCP Package Schema](https://adcontextprotocol.org/docs/):

```yaml
Package:
  type: object
  properties:
    buyer_ref:
      type: string
      description: "Buyer's reference identifier for this package"
      # This field exists specifically for the buyer to provide tracking IDs
```

**The spec includes `buyer_ref` specifically for buyers to provide tracking identifiers.** Wonderstruck should respect this field.

### Not a Spec Gap

This is not a missing field in the spec:
- ✅ `buyer_ref` is defined in the AdCP Package schema
- ✅ We're providing it in every package
- ❌ Wonderstruck is not using it

### Impact

Without using `buyer_ref`, Wonderstruck cannot:
1. **Provide unique package names** in their UI
2. **Support multi-package campaigns** (all packages get the same generic name)
3. **Enable buyer tracking** of specific packages
4. **Maintain audit trails** with meaningful identifiers

## Example Scenarios

### Scenario 1: Single Package Campaign
```json
{
  "promoted_offering": "Nike Shoes Q1",
  "packages": [{
    "buyer_ref": "nike_q1_display_728x90"
  }]
}
```

**Current (Wrong)**: "None - 1 packages"
**Expected**: "nike_q1_display_728x90" or "Nike Shoes Q1 - nike_q1_display_728x90"

### Scenario 2: Multi-Package Campaign
```json
{
  "promoted_offering": "Nike Shoes Q1",
  "packages": [
    {"buyer_ref": "nike_q1_display_728x90"},
    {"buyer_ref": "nike_q1_display_300x250"},
    {"buyer_ref": "nike_q1_video_preroll"}
  ]
}
```

**Current (Wrong)**: All three get "None - 3 packages"
**Expected**: Three distinct names using each `buyer_ref`

## Recommended Action

Wonderstruck should update their package name generation logic to:

1. **Read the `buyer_ref` field** from the package object
2. **Use it as the primary identifier** in the generated name
3. **Fall back to auto-generated names** only if `buyer_ref` is missing (for backward compatibility)

## Code Reference

Our implementation that generates and sends `buyer_ref`:

- **Schema Definition**: `src/core/schemas.py:1814` (Package.buyer_ref field)
- **Auto-Generation**: `src/core/schemas.py:1930` (CreateMediaBuyRequest validator)
- **Legacy Conversion**: `src/core/schemas.py:1915-1935` (product_ids → packages with buyer_ref)

## Contact

This issue should be raised with Wonderstruck's engineering team. The `buyer_ref` field is:
- ✅ Part of the AdCP spec
- ✅ Being sent correctly by us
- ❌ Not being used by them

---

**Classification**: Partner Bug (Not Spec Gap)
**Priority**: Medium (affects UX but not functionality)
**Blocker**: No (campaigns still execute, just with poor naming)
