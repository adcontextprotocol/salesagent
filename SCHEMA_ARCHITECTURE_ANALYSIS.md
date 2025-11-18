# Schema Architecture Analysis: Phase 5 Type Confusion

**Date:** 2025-11-17
**Analysis By:** Claude Code
**Question:** Is the schema type confusion just test issues, or a fundamental architectural flaw?

## Executive Summary

**Verdict: ARCHITECTURAL DESIGN FLAW**

The Phase 5 test failures reveal a **fundamental mismatch** between:
1. How we **construct** schema objects (using dicts)
2. What the **library schemas expect** (discriminated union instances)

This is NOT just test confusion - it's a systematic problem in `product_conversion.py` that affects production code.

---

## The Core Problem

### What Tests Are Revealing

```python
# Test error pattern:
pricing_options.0.CpmFixedRatePricingOption: Input should be a valid dictionary or instance of CpmFixedRatePricingOption
```

This error means: **Pydantic received a dict when it expected a typed object instance**.

### The Architectural Issue

Our `product_conversion.py` returns **dicts** for pricing_options:

```python
# src/core/product_conversion.py:11-50
def convert_pricing_option_to_adcp(pricing_option) -> dict:  # ❌ Returns dict!
    """Convert database PricingOption to AdCP pricing option discriminated union."""
    result = {
        "pricing_model": pricing_option.pricing_model.lower(),
        "currency": pricing_option.currency,
        "rate": float(pricing_option.rate),  # For fixed pricing
        # ... more dict fields
    }
    return result  # ❌ Plain dict, not a typed object
```

But the library Product expects **typed instances**:

```python
# adcp library (via inspection)
class Product(BaseModel):
    pricing_options: list[
        CpmFixedRatePricingOption |      # Must be instance!
        CpmAuctionPricingOption |        # Not dict!
        VcpmFixedRatePricingOption |
        # ... 6 more union types
    ]
```

### Why This Breaks

When we construct Product:

```python
# product_conversion.py:93-96
if product_model.pricing_options:
    product_data["pricing_options"] = [
        convert_pricing_option_to_adcp(po)  # ❌ Returns dict
        for po in product_model.pricing_options
    ]

return Product(**product_data)  # ❌ Pydantic validation fails!
```

**Pydantic's discriminated union handling:**
1. Receives a dict for `pricing_options[0]`
2. Tries to discriminate which union type it is (CPM fixed? CPM auction? etc.)
3. **Fails** because dicts don't match the discriminator pattern
4. Error: "Input should be a valid dictionary or instance of CpmFixedRatePricingOption"

---

## Evidence This Is Architectural

### 1. Production Code Uses This Pattern

```python
# src/core/product_conversion.py:53-128
def convert_product_model_to_schema(product_model) -> Product:
    """Convert database Product model to Product schema."""
    # ... build product_data dict ...

    # LINE 93-96: The problematic code
    if product_model.pricing_options:
        product_data["pricing_options"] = [
            convert_pricing_option_to_adcp(po)  # Returns dict!
            for po in product_model.pricing_options
        ]

    return Product(**product_data)  # This breaks!
```

This is called from:
- `get_products` tool (via product catalog providers)
- Database Product → API Product conversion
- **Production code paths**, not just tests

### 2. Library Schema Contract

The adcp library expects discriminated union instances:

```python
# From library inspection:
LibraryProduct.pricing_options: list[
    CpmFixedRatePricingOption |  # Must be typed instance
    CpmAuctionPricingOption |    # Cannot be plain dict
    # ... 7 more union types
]
```

### 3. Our Product Schema Extends Library

```python
# src/core/schemas.py:1095-1114
class Product(LibraryProduct):
    """Product schema extending library Product with internal fields."""

    # We inherit pricing_options field from LibraryProduct
    # Which means we inherit its discriminated union type

    implementation_config: dict[str, Any] | None = Field(
        default=None,
        exclude=True,  # Internal field
    )
```

**The inheritance means:**
- Our Product has same pricing_options type as LibraryProduct
- That type is a discriminated union of typed classes
- **We cannot pass dicts** - we must pass instances

---

## Root Cause Analysis

### Why We're Passing Dicts

Looking at `convert_pricing_option_to_adcp`:

```python
def convert_pricing_option_to_adcp(pricing_option) -> dict:
    """Returns: Dict representing AdCP pricing option"""
    result = {
        "pricing_model": pricing_option.pricing_model.lower(),
        "currency": pricing_option.currency,
        "pricing_option_id": f"{pricing_option.pricing_model.lower()}_{pricing_option.currency.lower()}_{'fixed' if pricing_option.is_fixed else 'auction'}",
    }

    if pricing_option.is_fixed and pricing_option.rate:
        result["rate"] = float(pricing_option.rate)
    elif not pricing_option.is_fixed and pricing_option.price_guidance:
        result["price_guidance"] = pricing_option.price_guidance

    return result  # ❌ Dict, not typed instance
```

**Why this was done:**
- Simpler to construct (just dict manipulation)
- Avoids importing 9 different pricing option types
- "Let Pydantic figure it out" approach

**Why this fails:**
- Pydantic discriminated unions need explicit type instances
- Dict discrimination doesn't work reliably
- Validation fails with cryptic error messages

### Schema Boundary Confusion

We have **three layers** of schema types:

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Database Models (SQLAlchemy)                       │
│  - models.Product                                            │
│  - models.PricingOption                                      │
│  - JSON columns, internal fields                             │
└─────────────────────────────────────────────────────────────┘
                        ↓ convert_product_model_to_schema()
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: Internal Schemas (src/core/schemas.py)             │
│  - schemas.Product(LibraryProduct)                           │
│  - Extends library with internal fields (exclude=True)       │
│  - Still expects library types for inherited fields!         │
└─────────────────────────────────────────────────────────────┘
                        ↓ model_dump()
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: AdCP Library Schemas (adcp package)                │
│  - LibraryProduct                                            │
│  - CpmFixedRatePricingOption, etc.                           │
│  - Discriminated unions, strict typing                       │
└─────────────────────────────────────────────────────────────┘
```

**The mistake:**
- We treat Layer 2 → Layer 3 conversion as "just dict manipulation"
- **But Layer 2 schemas INHERIT Layer 3 types!**
- So we must use Layer 3 typed instances, not dicts

---

## Where This Pattern Exists

### Files That Return Dicts for Typed Fields

1. **`src/core/product_conversion.py`** (PRIMARY ISSUE)
   - `convert_pricing_option_to_adcp()` → returns dict
   - `convert_product_model_to_schema()` → uses those dicts
   - Called by all product catalog providers

2. **Package Construction in Tests**
   - Tests build Package objects with dict packages
   - Should use PackageRequest instances

3. **Creative Response Construction**
   - Some responses build nested objects as dicts
   - Should use library Creative instances

---

## The Correct Pattern

### What We Should Do

```python
# ✅ CORRECT - Return typed instances
def convert_pricing_option_to_adcp(pricing_option) -> Union[
    CpmFixedRatePricingOption,
    CpmAuctionPricingOption,
    # ... all 9 types
]:
    """Convert database PricingOption to AdCP typed instance."""
    pricing_model = pricing_option.pricing_model.lower()

    # Discriminate on pricing_model + is_fixed
    if pricing_model == "cpm":
        if pricing_option.is_fixed:
            return CpmFixedRatePricingOption(
                pricing_model="cpm",
                currency=pricing_option.currency,
                pricing_option_id=f"cpm_{pricing_option.currency.lower()}_fixed",
                rate=float(pricing_option.rate),
                min_spend_per_package=pricing_option.min_spend_per_package,
            )
        else:
            return CpmAuctionPricingOption(
                pricing_model="cpm",
                currency=pricing_option.currency,
                pricing_option_id=f"cpm_{pricing_option.currency.lower()}_auction",
                price_guidance=pricing_option.price_guidance,
                min_spend_per_package=pricing_option.min_spend_per_package,
            )
    elif pricing_model == "vcpm":
        # ... similar for VCPM
    # ... handle all 9 pricing model types
```

### Why This Works

1. **Returns typed instances** that match library discriminated union
2. **Pydantic can validate** without type confusion
3. **Type safety** - mypy can check we're returning correct types
4. **Explicit** - no "let Pydantic figure it out" magic

---

## Impact Assessment

### Production Code Affected

1. **All product catalog providers** that call `convert_product_model_to_schema()`
   - Database provider
   - Hybrid provider
   - AI provider
   - Signals provider

2. **Get products tool** (`src/core/main.py`)
   - Returns Product objects to clients
   - **If any Product has pricing_options, validation fails**

3. **Product serialization** anywhere Product schema is used
   - Admin UI product listings
   - API product endpoints
   - Product validation in media buy creation

### Test Failures Explained

Phase 5 tests fail because they:
1. Create Product objects with pricing_options
2. Pass those products through validation
3. Pydantic rejects dict pricing_options
4. **Test reveals production bug**

---

## Recommended Fix

### Phase 5A: Fix product_conversion.py (HIGH PRIORITY)

1. **Rewrite `convert_pricing_option_to_adcp()`**
   - Import all 9 pricing option types from adcp library
   - Return typed instances based on discriminator (pricing_model + is_fixed)
   - Use factory pattern: `if pricing_model == "cpm" and is_fixed: return CpmFixedRatePricingOption(...)`

2. **Update return type annotation**
   ```python
   def convert_pricing_option_to_adcp(
       pricing_option
   ) -> Union[
       CpmFixedRatePricingOption,
       CpmAuctionPricingOption,
       VcpmFixedRatePricingOption,
       VcpmAuctionPricingOption,
       CpcPricingOption,
       CpcvPricingOption,
       CpvPricingOption,
       CppPricingOption,
       FlatRatePricingOption,
   ]:
   ```

3. **Add comprehensive unit tests**
   - Test each pricing model type
   - Verify instances validate against library schemas
   - Test roundtrip: DB → Schema → Dict → Schema

### Phase 5B: Fix Package Construction (MEDIUM PRIORITY)

1. **PackageRequest vs Package confusion**
   - Tests should use `PackageRequest` for create_media_buy
   - Responses should use `Package` (has package_id, status)
   - Never pass dicts - always use typed instances

2. **Update media_buy_create.py**
   - Line 1859-1871: Package construction from PackageRequest
   - Use proper PackageRequest → Package conversion
   - Don't rely on dict manipulation

### Phase 5C: Schema Documentation (LOW PRIORITY)

1. **Add architecture decision record (ADR)**
   - Document request vs response schema pattern
   - Explain when to use library types directly
   - When to extend library types

2. **Update CLAUDE.md**
   - Add section on discriminated union handling
   - Provide examples of correct conversion patterns

---

## Prevention Going Forward

### Code Review Checklist

When touching schema code, check:

1. ✅ **Are we constructing objects that extend library schemas?**
   - If yes → Use library typed instances, not dicts

2. ✅ **Are we returning objects with discriminated union fields?**
   - If yes → Return typed instances that match union types

3. ✅ **Are we converting database models to schemas?**
   - If yes → Import and use library types explicitly

4. ✅ **Does the conversion pass validation?**
   - Test: `Product(**data).model_dump()` → should not raise ValidationError

### Type Hints Matter

```python
# ❌ BAD - Hides the problem
def convert_pricing_option_to_adcp(pricing_option) -> dict:
    pass

# ✅ GOOD - Makes contract explicit
def convert_pricing_option_to_adcp(pricing_option) -> CpmFixedRatePricingOption | CpmAuctionPricingOption | ...:
    pass
```

### Pre-commit Hook Suggestion

Add hook that checks:
- Functions returning dicts for schema construction
- Warn if dict is passed to discriminated union field

---

## Conclusion

**This is NOT a test issue - it's an architectural design flaw.**

The root cause:
- `product_conversion.py` returns dicts for discriminated union fields
- Library schemas expect typed instances
- Pydantic validation fails with confusing error messages

The fix:
- Rewrite `convert_pricing_option_to_adcp()` to return typed instances
- Import and use all 9 library pricing option types
- Test roundtrip conversion thoroughly

**Priority:** HIGH - This affects all product-related operations in production.

**Estimated Effort:** 4-6 hours
- 2 hours: Rewrite conversion function with proper types
- 1 hour: Add comprehensive unit tests
- 1 hour: Test integration with product catalog providers
- 1-2 hours: Fix any edge cases discovered

---

## Appendix: Code Examples

### Current (Broken) Pattern

```python
# ❌ BROKEN
def convert_pricing_option_to_adcp(pricing_option) -> dict:
    return {
        "pricing_model": "cpm",
        "rate": 10.0,
        "currency": "USD",
    }

product_data["pricing_options"] = [
    convert_pricing_option_to_adcp(po) for po in product_model.pricing_options
]
Product(**product_data)  # ❌ ValidationError!
```

### Correct Pattern

```python
# ✅ CORRECT
from adcp.types.generated_poc.cpm_fixed_option import CpmFixedRatePricingOption

def convert_pricing_option_to_adcp(pricing_option) -> CpmFixedRatePricingOption | ...:
    if pricing_option.pricing_model.lower() == "cpm" and pricing_option.is_fixed:
        return CpmFixedRatePricingOption(
            pricing_model="cpm",
            rate=float(pricing_option.rate),
            currency=pricing_option.currency,
            pricing_option_id="cpm_usd_fixed",
        )
    # ... handle other types

product_data["pricing_options"] = [
    convert_pricing_option_to_adcp(po) for po in product_model.pricing_options
]
Product(**product_data)  # ✅ Validates successfully!
```

### The Key Difference

```python
# Dict (doesn't validate):
{"pricing_model": "cpm", "rate": 10.0, "currency": "USD"}

# Typed instance (validates):
CpmFixedRatePricingOption(pricing_model="cpm", rate=10.0, currency="USD")
```

**Pydantic needs the type information to validate discriminated unions!**
