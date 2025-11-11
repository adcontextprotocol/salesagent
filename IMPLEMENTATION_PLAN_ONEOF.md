# OneOf Error Handling - Implementation Plan

## Status: Phase 1 Complete ✅

This document tracks the implementation of AdCP PR #186 (oneOf error handling) in our codebase.

---

## ✅ Phase 1: Schema Updates (COMPLETED)

### JSON Schemas Updated
- [x] `schemas/v1/_schemas_v1_media-buy_create-media-buy-response_json.json`
  - Added oneOf with success/error branches
  - Success: requires `media_buy_id`, `buyer_ref`, `packages`
  - Error: requires `errors` array (min 1 item)
  - Mutual exclusion enforced via `not` constraints

- [x] `schemas/v1/_schemas_v1_media-buy_update-media-buy-response_json.json`
  - Added oneOf with success/error branches
  - Success: requires `media_buy_id`, `buyer_ref`
  - Error: requires `errors` array
  - Mutual exclusion enforced

### Pydantic Schemas Updated
- [x] `src/core/schemas.py` - Added Union import
- [x] `CreateMediaBuySuccess` - New success branch model
- [x] `CreateMediaBuyError` - New error branch model
- [x] `CreateMediaBuyResponse = Union[CreateMediaBuySuccess, CreateMediaBuyError]`
- [x] `UpdateMediaBuySuccess` - New success branch model
- [x] `UpdateMediaBuyError` - New error branch model
- [x] `UpdateMediaBuyResponse = Union[UpdateMediaBuySuccess, UpdateMediaBuyError]`

**Key Features:**
- Model validators enforce oneOf constraints
- `@model_validator(mode='after')` prevents mixed responses
- Success models forbid `errors` field
- Error models forbid success fields (`media_buy_id`, `buyer_ref`, etc.)
- Preserved `__str__()` methods for protocol envelope messages
- Preserved `model_dump()` / `model_dump_internal()` patterns

---

## 🔄 Phase 2: Tool Implementation Updates (IN PROGRESS)

### Strategy

The tool implementations need to be updated to return explicit success or error branches instead of optional fields.

**Current Pattern (BAD):**
```python
return CreateMediaBuyResponse(
    buyer_ref=request.buyer_ref,
    media_buy_id=media_buy.media_buy_id if media_buy else None,
    packages=packages if packages else [],
    errors=errors if errors else None
)
```

**New Pattern (GOOD):**
```python
# Success case: ALL constraints fulfilled
if all_constraints_fulfilled(media_buy, request):
    return CreateMediaBuySuccess(
        media_buy_id=media_buy.media_buy_id,
        buyer_ref=request.buyer_ref,
        packages=packages,
        creative_deadline=media_buy.creative_deadline
    )

# Error case: operation failed
else:
    return CreateMediaBuyError(
        errors=[Error(
            code="CONSTRAINT_FULFILLMENT_FAILED",
            message="Could not fulfill all targeting constraints",
            details={"unsupported": ["dayparting", "device_targeting"]}
        )]
    )
```

### Files to Update

#### 1. `src/core/tools/media_buy_create.py`
**Function:** `_create_media_buy_impl()`
**Return type:** Change from `CreateMediaBuyResponse` to `Union[CreateMediaBuySuccess, CreateMediaBuyError]`

**Return statements to update (5 locations):**
- Line 1290: Error case (missing tenant)
- Line 1704: Error case (validation failure)
- Line 2065: Error case (adapter failure)
- Line 2135: Error case (creative processing failure)
- Line 2228: Success case (media buy created)

**Key Changes:**
1. Update return type annotation
2. Convert error returns to `CreateMediaBuyError(...)`
3. Convert success returns to `CreateMediaBuySuccess(...)`
4. Add validation logic to ensure ALL constraints are fulfilled before success
5. Remove partial success logic (no media_buy_id with errors)

#### 2. `src/core/tools/media_buy_update.py`
**Function:** `_update_media_buy_impl()`
**Return type:** Change from `UpdateMediaBuyResponse` to `Union[UpdateMediaBuySuccess, UpdateMediaBuyError]`

**Similar changes as above.**

#### 3. Other Operations (Future)
- `build_creative` → BuildCreativeResponse (oneOf)
- `sync_creatives` → SyncCreativesResponse (special: dual-level errors)
- `provide_performance_feedback` → ProvidePerformanceFeedbackResponse (oneOf)
- `activate_signal` → ActivateSignalResponse (oneOf)

---

## 🧪 Phase 3: Test Updates (PENDING)

### Test Files to Update

#### Unit Tests
- [ ] `tests/unit/test_adcp_contract.py`
  - Add oneOf validation tests
  - Verify success/error branch validation
  - Test mutual exclusion constraints

- [ ] `tests/unit/test_create_media_buy.py` (if exists)
  - Update assertions to use type narrowing
  - Test both success and error branches explicitly

#### Integration Tests
- [ ] `tests/integration/test_create_media_buy_roundtrip.py`
  - Update to test Union type responses
  - Add tests for both success and error branches
  - Verify oneOf constraints in roundtrip

- [ ] `tests/integration/test_mcp_tool_roundtrip_minimal.py`
  - Update CreateMediaBuyResponse assertions
  - Use `isinstance(response, CreateMediaBuySuccess)` checks

#### E2E Tests
- [ ] `tests/e2e/test_schema_validation_standalone.py`
  - Verify responses validate against updated JSON schemas
  - Test oneOf validation with real data

### Test Pattern Changes

**Old Pattern:**
```python
def test_create_media_buy_success(integration_db):
    response = _create_media_buy_impl(...)

    assert response.media_buy_id is not None  # Could be None!
    assert response.errors is None  # Could have errors!
```

**New Pattern:**
```python
def test_create_media_buy_success(integration_db):
    response = _create_media_buy_impl(...)

    # Type narrowing
    assert isinstance(response, CreateMediaBuySuccess)
    assert response.media_buy_id  # Always present in success branch
    # No need to check errors - impossible in this branch

def test_create_media_buy_error(integration_db):
    response = _create_media_buy_impl(...)

    # Type narrowing
    assert isinstance(response, CreateMediaBuyError)
    assert len(response.errors) > 0
    # No need to check media_buy_id - impossible in error branch
```

---

## 📊 Phase 4: Validation & Testing (PENDING)

### Validation Steps
- [ ] Run unit tests: `uv run pytest tests/unit/`
- [ ] Run integration tests: `uv run pytest tests/integration/`
- [ ] Run E2E tests: `uv run pytest tests/e2e/`
- [ ] Run full suite: `./run_all_tests.sh ci`
- [ ] Verify AdCP schema compliance: `pytest tests/unit/test_adcp_contract.py -v`

### Expected Issues

1. **Type Checker Errors (mypy)**
   - Functions expecting `CreateMediaBuyResponse` now get Union type
   - Need to add type narrowing in callers
   - Use `isinstance()` checks before accessing branch-specific fields

2. **Test Failures**
   - Tests checking `response.media_buy_id is not None` will fail for Union type
   - Need to use type narrowing before assertions
   - Tests expecting partial success will fail (this is GOOD - intended behavior)

3. **Serialization Issues**
   - Union types serialize to one branch or the other
   - Protocol envelope needs to handle Union types
   - Testing hooks need to be applied to correct branch

---

## 🔧 Implementation Helpers

### Constraint Validation Helper

Add to `src/core/validation_helpers.py`:

```python
def validate_all_constraints_fulfilled(
    media_buy: MediaBuy,
    request: CreateMediaBuyRequest,
    adapter: BaseAdapter
) -> tuple[bool, list[Error]]:
    """Validate that ALL requested constraints were fulfilled.

    Per AdCP PR #186, we cannot return partial success. Either ALL
    constraints are fulfilled (success) or operation fails (error).

    Args:
        media_buy: Created media buy object
        request: Original request with constraints
        adapter: Adapter used for creation

    Returns:
        (success: bool, errors: list[Error])
    """
    errors = []

    # Check targeting constraints
    for package in request.packages:
        if package.targeting_overlay:
            targeting = package.targeting_overlay

            # Device targeting
            if targeting.device_type_any_of:
                if not adapter.supports_device_targeting:
                    errors.append(Error(
                        code="TARGETING_NOT_SUPPORTED",
                        message="Device targeting not supported by adapter",
                        details={"unsupported_feature": "device_type_any_of"}
                    ))

            # Dayparting
            if targeting.day_of_week or targeting.hour_of_day:
                if not adapter.supports_dayparting:
                    errors.append(Error(
                        code="TARGETING_NOT_SUPPORTED",
                        message="Dayparting not supported by adapter",
                        details={"unsupported_feature": "dayparting"}
                    ))

            # Add more constraint checks as needed...

    return (len(errors) == 0, errors)
```

### Type Narrowing Helper

Add to tests/conftest.py:

```python
from typing import TypeGuard
from src.core.schemas import (
    CreateMediaBuySuccess,
    CreateMediaBuyError,
    CreateMediaBuyResponse
)

def is_success_response(
    response: CreateMediaBuyResponse
) -> TypeGuard[CreateMediaBuySuccess]:
    """Type guard for success responses."""
    return isinstance(response, CreateMediaBuySuccess)

def is_error_response(
    response: CreateMediaBuyResponse
) -> TypeGuard[CreateMediaBuyError]:
    """Type guard for error responses."""
    return isinstance(response, CreateMediaBuyError)
```

---

## 📈 Progress Tracking

### Completed ✅
- JSON schema updates (create, update media buy)
- Pydantic schema models (Success/Error classes)
- Union type definitions
- Model validators for oneOf constraints

### In Progress 🔄
- Documentation and implementation planning

### Not Started 📋
- Tool implementation updates (5 return statements in create_media_buy)
- Tool implementation updates (update_media_buy)
- Test suite updates
- Integration testing
- Full validation run

### Estimated Timeline
- **Phase 2** (Tool Updates): 2-3 days
- **Phase 3** (Test Updates): 1-2 days
- **Phase 4** (Validation): 1 day
- **Total**: ~4-6 days

---

## 🚨 Breaking Changes

### API Changes
- `CreateMediaBuyResponse` is now a Union type
- Code checking `response.media_buy_id is not None` needs type narrowing
- No more partial success - operation succeeds OR fails

### Migration Path
1. **Update imports**: Add `CreateMediaBuySuccess`, `CreateMediaBuyError`
2. **Update type checks**: Use `isinstance(response, CreateMediaBuySuccess)`
3. **Update return statements**: Return explicit success/error branches
4. **Update tests**: Add type narrowing before field access

### Backward Compatibility
- ⚠️ **Breaking Change**: This is a breaking change to the response structure
- Existing code expecting optional `media_buy_id` will need updates
- Type checkers (mypy) will catch most issues
- Consider versioning the API endpoint if needed

---

## 📚 References

- **AdCP PR #186**: Atomic Operation Semantics
- **Analysis Document**: `/ANALYSIS_ONEOF_ERROR_HANDLING.md`
- **JSON Schemas**: `/schemas/v1/_schemas_v1_media-buy_*`
- **Pydantic Schemas**: `/src/core/schemas.py` (lines 2288-2640)

---

## Next Steps

1. **Complete Phase 2**: Update tool implementations
   - Start with `_create_media_buy_impl()`
   - Add constraint validation logic
   - Convert all return statements

2. **Begin Phase 3**: Update test suite
   - Add type narrowing helpers
   - Update unit tests first
   - Then integration tests

3. **Run Phase 4**: Full validation
   - Run test suite incrementally
   - Fix issues as they arise
   - Document any edge cases

**Ready to proceed with Phase 2 when you are!**
