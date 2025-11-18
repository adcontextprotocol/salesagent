# Test Failure Investigation - fix-product-properties Branch

## Summary

Investigated remaining test failures in CI (run 19450968945) after pricing option migration.

## Failures Fixed

### 1. get_pricing_option_id() helper (CRITICAL) ✅
- **File**: `tests/integration_v2/conftest.py:468`
- **Root Cause**: Helper was accessing `pricing_option.id` instead of `pricing_option.pricing_option_id`
- **Impact**: 7 test_minimum_spend_validation tests (setup errors)
- **Fix**: Changed line 470 from `return str(pricing_option.id)` to `return str(pricing_option.pricing_option_id)`
- **Status**: FIXED

### 2. CreateMediaBuySuccess Package schema validation ✅
- **File**: `tests/integration_v2/test_create_media_buy_roundtrip.py:132`
- **Root Cause**: adcp library's CreateMediaBuyResponse uses minimal Package schema with only `buyer_ref` and `package_id` fields. Test was trying to include `product_id`, `budget`, `status` which are not in the response schema.
- **Impact**: 1 test (test_create_media_buy_response_survives_testing_hooks_roundtrip)
- **Fix**: Updated test to only use fields that CreateMediaBuyResponse Package schema accepts
- **Note**: This is a quirk of the adcp library - CreateMediaBuyResponse has its own minimal Package type
- **Status**: FIXED

### 3. Missing is_fixed Field in Pricing Options ✅
- **File**: `src/core/schemas.py` (lines 1202-1244)
- **Root Cause**: adcp library's discriminated union types (CpmFixedRatePricingOption vs CpmAuctionPricingOption) don't have explicit `is_fixed` field. Type discrimination is done via class type, not a field. When serialized to JSON via `model_dump()`, type information is lost.
- **Impact**: Tests expect `is_fixed` field to distinguish fixed from auction pricing (e.g., `test_get_products_basic`)
- **Fix**: Added `@field_serializer("pricing_options", when_used="json")` to Product schema. Serializer adds `is_fixed` field based on presence of `rate` vs `price_guidance`:
  - Fixed pricing (has `rate`): `is_fixed=True`
  - Auction pricing (has `price_guidance`): `is_fixed=False`
  - Fallback to `True` if neither field present (most pricing is fixed)
- **Logic**:
  ```python
  if "rate" in option_dict and option_dict["rate"] is not None:
      option_dict["is_fixed"] = True  # Fixed pricing
  elif "price_guidance" in option_dict:
      option_dict["is_fixed"] = False  # Auction pricing
  else:
      option_dict["is_fixed"] = True  # Fallback
  ```
- **Status**: FIXED

## Pre-Existing Issues (Not Related to Pricing Options)

### 4. Authorized Properties Template Missing ⚠️
- **Files**:
  - `tests/integration_v2/test_admin_ui_data_validation.py::test_authorized_properties_no_duplicates_with_tags`
  - `tests/integration_v2/test_admin_ui_data_validation.py::test_authorized_properties_shows_all_properties`
- **Root Cause**: Template `authorized_properties_list.html` was deprecated (renamed to `.html.deprecated`). Authorized properties functionality has moved to `inventory_unified.html` with API endpoint.
- **Impact**: 2 tests trying to render old HTML template
- **Assessment**: This is pre-existing technical debt from UI refactoring, NOT related to pricing option changes
- **Recommendation**: Either restore template for tests or update tests to use new inventory_unified page
- **Status**: NOT FIXED (pre-existing issue)

## Other Failures to Investigate

Based on CI logs, there are additional failures in:

1. **test_create_media_buy_v24.py** - Multiple tests failing (5 tests)
   - Likely related to Package schema or pricing_option_id format

2. **test_creative_lifecycle_mcp.py** - Some tests failing
   - May be unrelated to pricing options

3. **test_signals_agent_workflow.py** - 1 test failing
   - `test_get_products_with_signals_success`
   - Need to investigate if related to Product schema changes

4. **test_get_products_filters.py** - 1 test failing
   - `test_products_have_correct_structure`
   - Likely related to Product schema changes

5. **test_mcp_endpoints_comprehensive.py** - 2 tests failing
   - May be related to Product serialization

## Next Steps

1. Investigate test_create_media_buy_v24.py failures (likely same root cause as #1 and #2)
2. Check test_get_products_filters.py::test_products_have_correct_structure
3. Check test_signals_agent_workflow.py failures
4. Decide on authorized_properties tests (skip or fix separately as pre-existing issue)

## Files Modified

- `/Users/brianokelley/Developer/salesagent/.conductor/nagoya-v5/tests/integration_v2/conftest.py` (line 470)
- `/Users/brianokelley/Developer/salesagent/.conductor/nagoya-v5/tests/integration_v2/test_create_media_buy_roundtrip.py` (lines 128-143)
