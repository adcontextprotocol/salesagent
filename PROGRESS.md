# CI Failures Fix Progress

## Context
Fixing CI test failures after introducing typed pricing option instances from adcp library.

## Fixes Completed

### 1. Product Conversion: implementation_config Field (Commit 59b64a1d)
**Problem**: `AttributeError: 'Product' object has no attribute 'implementation_config'`
- `convert_product_model_to_schema()` was importing library Product instead of our extended Product
- Our extended Product has `implementation_config` field, library Product doesn't

**Solution**:
- Changed import in `src/core/product_conversion.py` from `adcp.types.generated_poc.product.Product` to `src.core.schemas.Product`
- Added logic to include `implementation_config` in the product_data dict
- Used `hasattr()` checks to safely access effective_implementation_config

**Files Changed**: `src/core/product_conversion.py`

### 2. DeliveryType Enum Extraction (Commit 35051b4a)
**Problem**: `ValidationError: delivery_type Input should be 'guaranteed' or 'non_guaranteed'`
- Product.delivery_type is a DeliveryType enum from adcp library
- MediaPackage expects Literal["guaranteed", "non_guaranteed"] string
- `str(DeliveryType.guaranteed)` returns "DeliveryType.guaranteed" (wrong!)

**Solution**:
- Extract `.value` from enum when constructing MediaPackages
- Added enum detection with `hasattr(obj, "value")`
- Fixed in 2 locations: approval workflow (line 619) and main flow (line 2492)

**Files Changed**: `src/core/tools/media_buy_create.py`

## Issues Remaining (To Be Confirmed by CI)

### 1. FormatId Type Mismatch ⚠️ INVESTIGATING
**Error**: `Input should be a valid dictionary or instance of FormatId [input_type=FormatId]`

**Root Cause**: Two different FormatId classes being mixed
- Library FormatId: `adcp.types.generated_poc.format_id.FormatId`
- Our FormatId: `src.core.schemas.FormatId` (extends library FormatId)
- Pydantic strict validation sees them as different types

**Potential Solutions**:
1. Override format_ids annotation in Product to accept Union[LibraryFormatId, OurFormatId]
2. Use library FormatId directly (remove our extension)
3. Add Pydantic model config to allow subclass instances

**Status**: Waiting for CI to see if delivery_type fix resolved the FormatId errors (they may be related)

### 2. DetachedInstanceError (7 tests)
**Error**: `sqlalchemy.orm.exc.DetachedInstanceError: Parent instance <Product> is not bound to a Session`

**Affected**: `tests/integration_v2/test_minimum_spend_validation.py`

**Root Cause**: Accessing `product.pricing_options` relationship outside database session scope

**Solution**: Need to eagerly load pricing_options or keep session open

### 3. NameError: Product Not Defined
**Error**: `NameError: name 'Product' is not defined`

**Affected**: `tests/integration/test_inventory_profile_effective_properties.py`

**Solution**: Add missing import in test file

### 4. Missing is_fixed Field
**Error**: Pricing options missing `is_fixed` field in serialization

**Solution**: Ensure is_fixed is included in pricing option output

### 5. Creative Status Enum Comparison
**Error**: `assert <CreativeStatus.approved: 'approved'> == 'approved'`

**Solution**: Extract `.value` from CreativeStatus enum similar to DeliveryType fix

## Test Results

**Before Fixes**: Multiple test jobs failing
**After Fix 1 (59b64a1d)**: Pushed, waiting for CI
**After Fix 2 (35051b4a)**: Pushed, CI running...

## Next Steps

1. Wait for CI results to see which issues remain
2. Address remaining issues based on actual failures
3. Focus on most critical/widespread failures first
