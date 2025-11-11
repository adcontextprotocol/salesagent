# Root Cause Analysis: CI Test Failures (2025-11-11)

## Executive Summary

Three distinct issues caused CI failures in the inventory-profiles PR. All were caught by automated tests and fixed before merge, demonstrating the value of comprehensive test coverage.

## Issue 1: E2E Test Fixture Mismatch

### Symptoms
```
ERROR at setup of test_create_media_buy_with_profile_based_product_uses_profile_inventory
fixture 'integration_db' not found
```

### Root Cause
**Fixture scope mismatch between test directories.**

The E2E tests (`tests/e2e/`) attempted to use the `integration_db` fixture, which is only defined in `tests/integration/conftest.py` and not available to E2E tests.

### Why This Happened
1. Tests were initially written for `tests/integration/` directory
2. Tests were moved/copied to `tests/e2e/` without updating fixture references
3. The `integration_db` fixture creates isolated test databases per-test (via `tests/integration/conftest.py`)
4. E2E tests have a different fixture setup and use `db_session` instead

### Fix
Replace `integration_db` with `db_session` fixture in all E2E tests:
```python
# Before (wrong):
def test_something(integration_db, sample_tenant):

# After (correct):
def test_something(db_session, sample_tenant):
```

### Prevention
1. **Fixture documentation**: Document which fixtures are available in which test directories
2. **Consistent naming**: Use clear fixture names that indicate scope (`e2e_db`, `integration_db`, etc.)
3. **Linting rule**: Add pre-commit hook to detect cross-directory fixture usage

### Lesson Learned
**Test organization matters.** Different test types (unit, integration, e2e) have different fixture scopes and infrastructure requirements. Moving tests between directories requires careful review of dependencies.

---

## Issue 2: Template URL Validation Test Failure

### Symptoms
```
FAILED tests/integration/test_template_url_validation.py::test_all_template_url_for_calls_resolve
Template: add_product_gam.html
  url_for('inventory_profiles.preview_inventory_profile', tenant_id=tenant_id, profile_id=0)
  Error: Could not build url for endpoint... Did you forget to specify values ['profile_id']?
```

### Root Cause
**Test validator didn't know how to provide `profile_id` parameter for new inventory_profiles routes.**

The template validation test (`test_all_template_url_for_calls_resolve`) scans all templates for `url_for()` calls and attempts to build each URL to ensure the route exists. It has a hardcoded list of common parameters (`product_id`, `agent_id`, etc.) but didn't include `profile_id`.

### Why This Happened
1. New inventory_profiles blueprint added routes with `profile_id` parameter
2. Templates use `profile_id=0` as a placeholder that gets replaced in JavaScript
3. Test validator tried to validate these placeholder URLs and failed
4. The test wasn't updated when new route parameters were introduced

### Fix
Add `profile_id` to the list of known parameters in the validator:
```python
if "profile_id" in params:
    test_params["profile_id"] = 1  # profile_id is an integer
```

### Prevention
1. **Automated parameter detection**: Parse Flask route decorators to auto-discover parameters
2. **Template linting**: Add pre-commit hook to detect new `url_for()` patterns
3. **Documentation**: Document the pattern of JavaScript URL manipulation (placeholder + replace)

### Lesson Learned
**Test infrastructure needs maintenance.** When adding new routes with new parameter patterns, related test infrastructure (validators, fixtures, etc.) must be updated too.

---

## Issue 3: Generated Schema Breaking Change (Merged from separate PR)

### Symptoms
```
FAILED test_schema_generated_compatibility.py::test_create_media_buy_response_compatible
'CreateMediaBuyResponse' object has no attribute 'buyer_ref'

FAILED test_schema_generated_compatibility.py::test_update_media_buy_response_compatible
'UpdateMediaBuyResponse' object has no attribute 'media_buy_id'
```

### Root Cause
**Generated schemas changed from simple Pydantic models to `RootModel` with union types, breaking test assertions.**

The AdCP schema generator updated CreateMediaBuyResponse and UpdateMediaBuyResponse to use Pydantic `RootModel` with union types (success | error):

```python
# Old structure:
class CreateMediaBuyResponse(BaseModel):
    buyer_ref: str
    media_buy_id: str | None
    # ...

# New structure:
class CreateMediaBuyResponse(RootModel[CreateMediaBuyResponse1 | CreateMediaBuyResponse2]):
    root: CreateMediaBuyResponse1 | CreateMediaBuyResponse2

class CreateMediaBuyResponse1(BaseModel):  # Success case
    buyer_ref: str
    media_buy_id: str
    # ...

class CreateMediaBuyResponse2(BaseModel):  # Error case
    errors: list[Error]
```

Tests accessed fields directly (`generated.buyer_ref`) but now need to access via `.root` (`generated.root.buyer_ref`).

### Why This Happened
1. **Schema evolution**: AdCP spec changed to enforce atomic semantics (success OR error, never both)
2. **Generator update**: The `datamodel-codegen` tool was updated to use `RootModel` for union types
3. **Silent schema updates**: Schema files updated automatically without triggering test updates
4. **Indirect dependency**: Changes came from merging the `fix-brand-manifest-validation` branch which included schema updates

### Fix
Update compatibility tests to access fields via `.root` for RootModel types:
```python
# Before (broken):
assert generated.buyer_ref == "test_ref_123"

# After (fixed):
assert generated.root.buyer_ref == "test_ref_123"
```

### Prevention
1. **Schema change detection**: Add pre-commit hook to detect `RootModel` introduction in generated schemas
2. **Compatibility test coverage**: Add tests that validate field access patterns for both simple and union types
3. **Schema version tracking**: Track generator version and schema structure changes in metadata
4. **Documentation**: Document the RootModel pattern and when it's used

### Why This Is Significant
This represents a **breaking change in the AdCP protocol**:
- **Before**: Responses could have both success data AND errors (non-atomic)
- **After**: Responses have EITHER success data OR errors (atomic)

This enforces better semantics but requires all clients to handle the union type correctly. This is the kind of change that needs careful coordination across the ecosystem.

### Lesson Learned
**Generated code changes are real code changes.** When schema generators update, treat it like any other breaking change:
1. Review the generated diff carefully
2. Update dependent code (tests, usage patterns)
3. Document the breaking change
4. Consider API versioning if needed

---

## Common Themes

### 1. Test Infrastructure as Code
All three issues involved test infrastructure (fixtures, validators, compatibility checks). This infrastructure needs the same care as production code:
- **Documentation**: What fixtures exist, where they work, what they do
- **Maintenance**: Update when adding new routes, parameters, or patterns
- **Evolution**: Keep pace with schema and framework changes

### 2. Cross-Cutting Changes
Changes that affect multiple components (new routes → templates → validators → tests) are riskier:
- **Checklists**: Create checklists for common change types
- **Automated detection**: Use linting/hooks to catch missing updates
- **Code review**: Explicitly review cross-cutting impacts

### 3. Schema Evolution Challenges
Generated schemas introduce unique challenges:
- **Silent updates**: Generator runs can change code without explicit commits
- **Breaking changes**: Union types, RootModels, and other structural changes break existing code
- **Versioning**: Need clear strategy for schema version management

## Recommendations

### Short Term (Immediate)
1. ✅ **Fixed**: Update E2E tests to use correct fixtures
2. ✅ **Fixed**: Add `profile_id` to template validator
3. ✅ **Fixed**: Update schema compatibility tests for RootModel

### Medium Term (Next Sprint)
1. **Document fixture scopes**: Add `docs/testing/fixtures-reference.md`
2. **Pre-commit hook**: Detect cross-directory fixture usage
3. **Template validation**: Auto-discover route parameters from Flask decorators
4. **Schema change detection**: Hook to detect RootModel introduction

### Long Term (Next Quarter)
1. **Schema versioning strategy**: How to handle breaking schema changes
2. **Generated code review**: Process for reviewing generator updates
3. **Test infrastructure audit**: Comprehensive review of all test utilities
4. **Cross-cutting change checklist**: Template for multi-component changes

## Conclusion

All three failures were caught by automated tests before merge, demonstrating the value of comprehensive CI. The fixes were straightforward once root causes were identified. The real value is in understanding **why** these happened and **how to prevent** similar issues in the future.

**Key Takeaway**: Test infrastructure deserves the same engineering rigor as production code. It's not "just tests" - it's the safety net that lets us move fast without breaking things.
