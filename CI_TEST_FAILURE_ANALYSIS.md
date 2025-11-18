# CI Test Failure Root Cause Analysis
**Date**: 2025-11-17
**Scope**: 35 failing tests in CI
**Branch**: fix-product-properties

## Executive Summary

After analyzing the failing tests, I've identified **5 major root cause categories** affecting 35 tests:

1. **Missing pricing_option_id** (8+ tests) - Tests using old factory patterns that don't include auto-generated pricing_option_id
2. **PackageRequest.model_dump_internal() doesn't exist** (4 tests) - Using internal methods on adcp library schemas
3. **list_creatives returning empty** (8 tests) - Header mock not working properly
4. **Wrong pricing_option_id format** (6 tests) - Hardcoding 'test_pricing_option' instead of generated format
5. **Schema confusion** (9+ tests) - Mixing request/response schemas, internal/library schemas

---

## Root Cause Category 1: Missing pricing_option_id

### Problem
Tests are not including `pricing_option_id` in package requests, causing AdCP spec validation to fail.

### Error Pattern
```
packages.0.pricing_option_id: Required field is missing
```

### Root Cause
**Factory misuse**: Tests are creating package dicts manually instead of using `create_test_package_request_dict()` from `tests/helpers/adcp_factories.py`.

The factory provides the correct default:
```python
# tests/helpers/adcp_factories.py:686
def create_test_package_request_dict(
    buyer_ref: str = "test_package_ref",
    product_id: str = "test_product",
    pricing_option_id: str = "cpm_option_1",  # <-- Default provided
    budget: float = 10000.0,
    **kwargs,
) -> dict[str, Any]:
```

But tests are doing this instead:
```python
# ❌ WRONG - Missing pricing_option_id
packages=[
    {
        "package_id": "pkg1",
        "products": ["error_test_product"],
        "budget": 5000.0,  # Only has budget, missing pricing_option_id
    }
]
```

### Affected Tests (8+)
- `tests/integration_v2/test_a2a_error_responses.py::TestA2AErrorPropagation::test_create_media_buy_validation_error_includes_errors_field`
- `tests/integration_v2/test_a2a_error_responses.py::TestA2AErrorPropagation::test_create_media_buy_insufficient_budget_returns_error`
- `tests/integration_v2/test_a2a_error_responses.py::TestA2AErrorPropagation::test_create_media_buy_invalid_product_id_returns_error`
- `tests/integration_v2/test_error_paths.py::TestCreateMediaBuyErrorPaths::test_missing_principal_returns_authentication_error`
- `tests/integration_v2/test_error_paths.py::TestCreateMediaBuyErrorPaths::test_start_time_in_past_returns_validation_error`
- `tests/integration_v2/test_error_paths.py::TestCreateMediaBuyErrorPaths::test_end_time_before_start_returns_validation_error`
- `tests/integration_v2/test_error_paths.py::TestCreateMediaBuyErrorPaths::test_missing_packages_returns_validation_error`
- `tests/integration/test_mcp_endpoints_comprehensive.py::TestMCPEndpointsComprehensive::test_create_media_buy_with_custom_fields`

### Fix
Replace manual package dict construction with factory:
```python
# ✅ CORRECT - Use factory
from tests.helpers.adcp_factories import create_test_package_request_dict

packages = [
    create_test_package_request_dict(
        buyer_ref="pkg1",
        product_id="error_test_product",
        pricing_option_id="cpm_usd_1",  # Must match actual PricingOption.id format
        budget=5000.0,
    )
]
```

**IMPORTANT**: The `pricing_option_id` must match the actual database PricingOption.id value, which is auto-generated as an integer (e.g., "123"). Tests using fixtures like `setup_test_tenant` should use `setup_test_tenant["pricing_option_id_usd"]` instead of hardcoded values.

---

## Root Cause Category 2: PackageRequest.model_dump_internal() Doesn't Exist

### Problem
Tests are calling `.model_dump_internal()` on `PackageRequest` objects, but this method doesn't exist because `PackageRequest` is from the adcp library.

### Error Pattern
```
AttributeError: 'PackageRequest' object has no attribute 'model_dump_internal'
```

### Root Cause
**Schema confusion**: Tests are treating `PackageRequest` (from adcp library) as if it were our internal schema with custom methods.

From `src/core/schemas.py`:
```python
from adcp.types.generated_poc.package_request import PackageRequest as LibraryPackageRequest

class PackageRequest(LibraryPackageRequest):
    """Extends adcp library PackageRequest with internal fields."""
    tenant_id: str | None = Field(None, exclude=True)  # Internal field
```

Our `PackageRequest` **extends** the library version but doesn't add `model_dump_internal()` - only response models have that method.

### Code Pattern in Failing Tests
```python
# tests/integration_v2/test_create_media_buy_v24.py:248
packages = [
    PackageRequest(
        buyer_ref="pkg_budget_test",
        product_id=setup_test_tenant["product_id_usd"],
        pricing_option_id=setup_test_tenant["pricing_option_id_usd"],
        budget=5000.0,
    )
]

# ❌ WRONG - PackageRequest doesn't have model_dump_internal()
response = await _create_media_buy_impl(
    packages=[p.model_dump_internal() for p in packages],  # <-- FAILS HERE
    ...
)
```

### Affected Tests (4)
- `tests/integration_v2/test_create_media_buy_v24.py::TestCreateMediaBuyV24Serialization::test_create_media_buy_with_package_budget_mcp`
- `tests/integration_v2/test_create_media_buy_v24.py::TestCreateMediaBuyV24Serialization::test_create_media_buy_with_targeting_overlay_mcp`
- `tests/integration_v2/test_create_media_buy_v24.py::TestCreateMediaBuyV24Serialization::test_create_media_buy_multiple_packages_with_budgets_mcp`
- `tests/integration_v2/test_create_media_buy_v24.py::TestCreateMediaBuyV24Serialization::test_create_media_buy_with_package_budget_a2a`

### Fix
Use `.model_dump()` instead (standard Pydantic method):
```python
# ✅ CORRECT - Use standard model_dump()
response = await _create_media_buy_impl(
    packages=[p.model_dump() for p in packages],  # Standard Pydantic method
    ...
)
```

**Rationale**: `model_dump()` is the standard Pydantic method for serializing to dict. Only our **response** models (Package, Creative, etc.) have `model_dump_internal()` for excluding internal fields. **Request** models like PackageRequest don't need it because they don't have internal fields that need hiding from clients.

---

## Root Cause Category 3: list_creatives Returning Empty List

### Problem
All 8 tests in `test_creative_lifecycle_mcp.py` are failing because `list_creatives` returns an empty list even though creatives exist in the database.

### Error Pattern
```python
assert 0 == 5  # Expected 5 creatives, got 0
```

### Root Cause
**Header mock not working**: The patch for `get_principal_id_from_context` is applied, but the actual header extraction in the tool is failing.

Looking at the test setup:
```python
# tests/integration_v2/test_creative_lifecycle_mcp.py:35-42
class MockContext:
    """Mock FastMCP Context for testing."""
    def __init__(self, auth_token="test-token-123"):
        if auth_token is None:
            self.meta = {"headers": {}}
        else:
            self.meta = {"headers": {"x-adcp-auth": auth_token}}
```

The mock sets `ctx.meta["headers"]["x-adcp-auth"]` but the actual tool likely accesses `ctx.headers` directly:
```python
# Likely implementation in src/core/tools/creatives.py
def list_creatives_raw(..., ctx):
    auth_token = ctx.headers.get("x-adcp-auth")  # ❌ ctx.headers, not ctx.meta["headers"]
    ...
```

### Affected Tests (8)
All tests in `tests/integration_v2/test_creative_lifecycle_mcp.py`:
- `test_sync_creatives_create_new_creatives`
- `test_sync_creatives_upsert_existing_creative`
- `test_list_creatives_basic`
- `test_list_creatives_with_filters`
- `test_list_creatives_with_creative_ids`
- `test_list_creatives_with_package_refs`
- `test_list_creatives_with_created_after`
- `test_create_media_buy_with_creative_ids`

### Fix Option 1: Fix MockContext to match actual FastMCP context
```python
class MockContext:
    """Mock FastMCP Context for testing."""
    def __init__(self, auth_token="test-token-123"):
        # FastMCP context has headers at top level, not in meta
        self.headers = {"x-adcp-auth": auth_token} if auth_token else {}
        self.meta = {"headers": self.headers}  # Keep both for compatibility
```

### Fix Option 2: Check actual FastMCP Context structure
Read `src/core/tools/creatives.py` to see how it accesses headers, then adjust MockContext accordingly.

### Investigation Needed
1. Check `list_creatives_raw()` implementation in `src/core/tools/creatives.py`
2. Verify how it extracts auth token from context
3. Check if `get_principal_id_from_context` helper is working correctly
4. The patch on line 197 might not be reaching the actual code path

---

## Root Cause Category 4: Wrong pricing_option_id Format

### Problem
Tests are using hardcoded `pricing_option_id="test_pricing_option"` but the actual database uses auto-generated integer IDs (e.g., "123").

### Error Pattern
```
Product prod_global does not offer pricing_option_id 'test_pricing_option'.
Available options: cpm_usd_1 (CPM, USD, $10.00)
```

### Root Cause
**Hardcoded test values**: Tests are using factory default values instead of retrieving actual generated pricing_option_id from fixtures.

From `tests/helpers/adcp_factories.py`:
```python
def create_test_package_request(
    pricing_option_id: str = "test_pricing_option",  # <-- This default is WRONG
    ...
)
```

But the actual pricing_option_id is generated when creating PricingOption:
```python
# tests/integration_v2/conftest.py (create_test_product_with_pricing)
pricing_option = PricingOption(
    tenant_id=tenant_id,
    product_id=product_id,
    pricing_model=pricing_model_lower,
    rate=rate_decimal,
    # id is auto-generated by database (primary key)
)
session.add(pricing_option)
session.flush()
# pricing_option.id now has the generated integer ID
```

### Affected Tests (6)
- `tests/integration_v2/test_minimum_spend_validation.py::TestMinimumSpendValidation::test_minimum_spend_validation_below_currency_limit`
- `tests/integration_v2/test_minimum_spend_validation.py::TestMinimumSpendValidation::test_minimum_spend_validation_below_product_override`
- `tests/integration_v2/test_minimum_spend_validation.py::TestMinimumSpendValidation::test_minimum_spend_validation_meets_currency_limit`
- `tests/integration_v2/test_minimum_spend_validation.py::TestMinimumSpendValidation::test_minimum_spend_validation_meets_product_override`
- `tests/integration_v2/test_minimum_spend_validation.py::TestMinimumSpendValidation::test_multiple_currencies_validated_separately`
- `tests/integration_v2/test_minimum_spend_validation.py::TestMinimumSpendValidation::test_maximum_daily_spend_validation`

### Fix
Tests must retrieve the actual pricing_option_id from the fixture or database:
```python
# ❌ WRONG - Hardcoded pricing_option_id
pkg = create_test_package_request(
    product_id="prod_global",
    pricing_option_id="test_pricing_option",  # Doesn't exist!
    budget=500.0,
)

# ✅ CORRECT - Use actual pricing_option_id from fixture
# In fixture setup:
with get_db_session() as session:
    product = create_test_product_with_pricing(...)
    session.flush()
    pricing_option_id = str(product.pricing_options[0].id)  # Get generated ID

# In test:
pkg = create_test_package_request(
    product_id="prod_global",
    pricing_option_id=pricing_option_id,  # Use actual ID
    budget=500.0,
)
```

**Pattern for fixtures**: Return pricing_option_id along with product_id:
```python
@pytest.fixture
def setup_test_data(self, integration_db):
    # ... create product with pricing ...

    yield {
        "product_id": product.product_id,
        "pricing_option_id": str(product.pricing_options[0].id),  # Include this!
    }
```

---

## Root Cause Category 5: Schema Confusion

### Problem
Tests are mixing request schemas with response schemas, or using internal schemas where library schemas are expected.

### Error Patterns
1. `packages: Extra inputs are not permitted` - Request schema has response-only fields
2. `delivery_measurement: Field required` - Using internal Product where library Product expected
3. `pricing_options type mismatch` - Wrong schema type for field

### Root Cause
**Multiple schema types**: We have:
1. **Library schemas** (from `adcp` package) - Canonical AdCP spec schemas
2. **Internal schemas** (in `src/core/schemas.py`) - Extend library with internal fields
3. **Request schemas** (`PackageRequest`) - For creating resources
4. **Response schemas** (`Package`) - For returning resources

Tests are confusing these types.

### Specific Issues

#### Issue 5A: Extra fields in request schemas (3 tests)
```python
# ❌ WRONG - Package response schema used in request
from src.core.schemas import Package  # Response schema!

request = {
    "packages": [
        Package(  # Has status, package_id, etc.
            package_id="pkg1",
            status="active",  # <-- Response-only field!
            products=["prod1"],
        )
    ]
}
```

**Affected tests**:
- `tests/integration_v2/test_a2a_skill_invocation.py::test_create_media_buy_skill_invocation`
- `tests/integration_v2/test_create_media_buy_roundtrip.py::test_create_media_buy_response_survives_testing_hooks_roundtrip`
- `tests/e2e/test_mcp_endpoints_roundtrip.py` (multiple)

**Fix**: Use `PackageRequest` for creating, `Package` for responses:
```python
# ✅ CORRECT
from src.core.schemas import PackageRequest

request = {
    "packages": [
        PackageRequest(  # Request schema - no status/package_id
            buyer_ref="pkg1",
            product_id="prod1",
            pricing_option_id="cpm_usd_1",
            budget=1000.0,
        ).model_dump()
    ]
}
```

#### Issue 5B: Internal Product vs Library Product (2 tests)
```python
# ❌ WRONG - Using internal Product where library Product expected
from src.core.schemas import Product  # Internal schema with extra fields!

product = Product(
    product_id="test",
    # ... missing required library fields like delivery_measurement
)
```

**Affected tests**:
- `tests/integration_v2/test_creative_lifecycle_mcp.py::test_create_media_buy_with_creative_ids`

**Fix**: Use library Product from adcp package:
```python
# ✅ CORRECT
from adcp.types.generated_poc.product import Product as LibraryProduct
from tests.helpers.adcp_factories import create_test_product

product = create_test_product(  # Factory handles all required fields
    product_id="test",
    delivery_measurement={"provider": "test", "notes": "test"},
    # ... all required fields
)
```

#### Issue 5C: pricing_options type mismatch (4 tests)
```python
# ❌ WRONG - pricing_options as list of dicts instead of PricingOption models
product = Product(
    pricing_options=[
        {"pricing_model": "cpm", "rate": 10.0}  # Dict, not discriminated union!
    ]
)
```

**Affected tests**:
- Various tests not using `create_test_cpm_pricing_option()` factory

**Fix**: Use factory for proper discriminated union format:
```python
# ✅ CORRECT
from tests.helpers.adcp_factories import create_test_cpm_pricing_option

product = Product(
    pricing_options=[
        create_test_cpm_pricing_option(
            pricing_option_id="cpm_1",
            rate=10.0,
            currency="USD",
        )
    ]
)
```

---

## Recommended Fix Strategy

### Phase 1: Fix Factory Misuse (8+ tests)
**Priority**: HIGH
**Effort**: LOW
**Files**: `test_a2a_error_responses.py`, `test_error_paths.py`, `test_mcp_endpoints_comprehensive.py`

1. Replace manual package dicts with `create_test_package_request_dict()`
2. Ensure `pricing_option_id` is passed correctly from fixtures
3. Run tests to verify: `pytest tests/integration_v2/test_error_paths.py -v`

### Phase 2: Fix PackageRequest.model_dump_internal() (4 tests)
**Priority**: HIGH
**Effort**: LOW
**Files**: `test_create_media_buy_v24.py`

1. Replace `.model_dump_internal()` with `.model_dump()`
2. Verify PackageRequest serialization works
3. Run tests: `pytest tests/integration_v2/test_create_media_buy_v24.py -v`

### Phase 3: Fix pricing_option_id Format (6 tests)
**Priority**: HIGH
**Effort**: MEDIUM
**Files**: `test_minimum_spend_validation.py`

1. Update fixture to return `pricing_option_id` along with `product_id`
2. Update tests to use fixture values instead of hardcoded "test_pricing_option"
3. Verify fixture queries database correctly: `str(product.pricing_options[0].id)`
4. Run tests: `pytest tests/integration_v2/test_minimum_spend_validation.py -v`

### Phase 4: Fix list_creatives Mock (8 tests)
**Priority**: MEDIUM
**Effort**: MEDIUM
**Files**: `test_creative_lifecycle_mcp.py`

1. Investigate `list_creatives_raw()` header extraction
2. Fix `MockContext` to match actual FastMCP context structure
3. Verify `get_principal_id_from_context` patch is reaching code
4. Run tests: `pytest tests/integration_v2/test_creative_lifecycle_mcp.py -v`

### Phase 5: Fix Schema Confusion (9+ tests)
**Priority**: MEDIUM
**Effort**: HIGH
**Files**: `test_a2a_skill_invocation.py`, `test_create_media_buy_roundtrip.py`, others

1. Identify which schema type each test needs (request vs response, internal vs library)
2. Replace incorrect schema usage with correct type
3. Use factories to avoid manual schema construction
4. Run affected tests individually to verify

---

## Systematic Test Patterns to Enforce

### Pattern 1: Always use factories for complex objects
```python
# ❌ DON'T manually construct
package = {"buyer_ref": "pkg1", "product_id": "prod1", ...}

# ✅ DO use factory
from tests.helpers.adcp_factories import create_test_package_request_dict
package = create_test_package_request_dict(buyer_ref="pkg1", product_id="prod1")
```

### Pattern 2: Get pricing_option_id from fixtures
```python
# ❌ DON'T hardcode
pricing_option_id = "test_pricing_option"

# ✅ DO retrieve from fixture
@pytest.fixture
def setup_data(integration_db):
    product = create_test_product_with_pricing(...)
    yield {"pricing_option_id": str(product.pricing_options[0].id)}

def test_something(setup_data):
    pricing_option_id = setup_data["pricing_option_id"]
```

### Pattern 3: Use correct schema type
```python
# ❌ DON'T use response schema for requests
from src.core.schemas import Package
request = {"packages": [Package(...)]}

# ✅ DO use request schema for requests
from src.core.schemas import PackageRequest
request = {"packages": [PackageRequest(...).model_dump()]}
```

### Pattern 4: Use standard Pydantic methods
```python
# ❌ DON'T use internal methods on library schemas
packages = [pkg.model_dump_internal() for pkg in library_packages]

# ✅ DO use standard Pydantic methods
packages = [pkg.model_dump() for pkg in packages]
```

---

## Pre-Commit Hook Recommendations

Add checks to prevent these issues:

1. **Check for hardcoded pricing_option_id**:
   ```bash
   grep -r 'pricing_option_id.*=.*"test_pricing_option"' tests/
   ```

2. **Check for model_dump_internal on library schemas**:
   ```bash
   grep -r 'PackageRequest.*model_dump_internal' tests/
   ```

3. **Check for missing pricing_option_id in package dicts**:
   ```bash
   # Scan for package dicts without pricing_option_id
   ```

4. **Verify factory usage**:
   ```python
   # Enforce use of create_test_package_request_dict for package creation
   ```

---

## Conclusion

All 35 test failures stem from **5 systematic issues**:

1. **Factory misuse** - Not using `create_test_package_request_dict()`
2. **Schema method confusion** - Using `model_dump_internal()` on library schemas
3. **Mock setup issues** - MockContext not matching actual FastMCP structure
4. **Hardcoded test values** - Not retrieving auto-generated pricing_option_id
5. **Schema type confusion** - Mixing request/response and internal/library schemas

**Recommendation**: Fix in phases 1-2 first (12 tests, LOW effort) to get quick wins, then tackle phases 3-5 for remaining tests.

**Long-term**: Improve factories and add pre-commit checks to prevent these patterns from recurring.
