# Migration Blockers: AdCP v1.2.1 Library Adoption

**Status**: ⚠️ BLOCKED - Requires Code Changes
**Date**: 2025-11-09
**Package Tested**: adcp==1.2.1 (with PR #23 oneOf patterns)

## Executive Summary

The adcp v1.2.1 library is correctly implemented and ready to use. However, **our codebase does not yet conform to the strict AdCP spec** that the library enforces. Migration is blocked until we fix our code to be spec-compliant.

**Key Finding**: ✅ adcp v1.2.1 is CORRECT, ❌ our code is NON-COMPLIANT

## Validation Errors Discovered

### Error 1: Package.status Required

**AdCP Spec**: `Package.status` is a required field
**Our Code**: Does not always provide status when creating Package objects

```python
# ❌ FAILS with adcp v1.2.1
CreateMediaBuySuccess(
    media_buy_id="mb_123",
    buyer_ref="ref_456",
    packages=[{
        "package_id": "pkg_1",
        # Missing "status" field!
    }],
)

# ValidationError: packages.0.status - Field required
```

**Locations That Need Fixing**:
-  `src/adapters/mock_ad_server.py:799` - _create_media_buy_immediate()
- All 5 adapters when constructing package responses
- ~20-30 locations total

**Fix Required**:
```python
# ✅ CORRECT
packages=[{
    "package_id": "pkg_1",
    "status": "active",  # Required by AdCP spec
}]
```

### Error 2: creative_deadline Type Mismatch

**AdCP Spec**: `creative_deadline` must be ISO 8601 string or null
**Our Code**: Passes Python `datetime` objects

```python
# ❌ FAILS with adcp v1.2.1
CreateMediaBuySuccess(
    media_buy_id="mb_123",
    buyer_ref="ref_456",
    packages=[...],
    creative_deadline=datetime.now(UTC),  # datetime object
)

# ValidationError: creative_deadline - Input should be a valid string
```

**Locations That Need Fixing**:
- All adapters when setting creative_deadline
- ~10-15 locations total

**Fix Required**:
```python
# ✅ CORRECT
creative_deadline=datetime.now(UTC).isoformat()  # ISO 8601 string
```

## Why This Happened

Our local type definitions were **too lenient**:
- Allowed optional fields where AdCP spec requires them
- Accepted Python objects where spec requires strings
- Had relaxed validation for development convenience

The adcp library correctly implements the **strict AdCP spec**, exposing our non-compliance.

## Impact Analysis

### What Works ✅
- adcp v1.2.1 package installs correctly
- All oneOf types (Success/Error) are present
- Union types work correctly
- Basic type imports successful
- 936/937 unit tests still pass with our local types

### What's Blocked ❌
- Cannot replace our Success/Error types with adcp types
- Cannot use adcp Package type (requires status field)
- Cannot use adcp response types (require ISO 8601 strings)
- Full migration blocked until code is spec-compliant

## Required Pre-Migration Work

### Phase 1: Fix Package Status (20-30 locations)

**Files to Update**:
```
src/adapters/mock_ad_server.py
src/adapters/google_ad_manager.py
src/adapters/kevel.py
src/adapters/triton_digital.py
src/adapters/xandr.py
```

**Pattern to Find**:
```bash
# Find all places that create package dicts without status
grep -r "package_id" src/adapters/ | grep -v "status"
```

**Fix**:
```python
# Before
package_response = {
    "package_id": package_id,
    "buyer_ref": package.buyer_ref,
}

# After
package_response = {
    "package_id": package_id,
    "buyer_ref": package.buyer_ref,
    "status": "active",  # Add required field
}
```

### Phase 2: Fix Datetime Serialization (10-15 locations)

**Pattern to Find**:
```bash
# Find all places that set creative_deadline with datetime object
grep -r "creative_deadline.*datetime" src/
```

**Fix**:
```python
# Before
creative_deadline = datetime.now(UTC) + timedelta(days=7)

# After
creative_deadline = (datetime.now(UTC) + timedelta(days=7)).isoformat()
```

### Phase 3: Test with adcp Types

After fixing:
1. Re-run attempt to use adcp types as base classes
2. Run full test suite
3. Fix any remaining validation errors
4. Verify AdCP compliance

## Estimated Effort

**Phase 1 (Package Status)**:
- Find all locations: 1 hour
- Fix and test each: 2-3 hours
- Total: ~4 hours

**Phase 2 (Datetime Serialization)**:
- Find all locations: 30 min
- Fix and test each: 1-2 hours
- Total: ~2 hours

**Phase 3 (Integration)**:
- Update type inheritance: 1 hour
- Test suite validation: 2 hours
- Fix edge cases: 2-3 hours
- Total: ~5 hours

**Grand Total**: 10-12 hours

## Alternative Approach: Gradual Migration

Instead of fixing everything at once, we could:

1. **Keep our local types for now** - They work, just aren't spec-perfect
2. **Import only non-conflicting types** - Use adcp for types we don't customize
3. **Fix spec compliance incrementally** - One adapter at a time
4. **Migrate types as code becomes compliant** - Gradual cutover

This reduces risk and allows us to ship the oneOf implementation we have now.

## Recommendation

**Option A: Ship Current Implementation** (Recommended)
- ✅ Our oneOf implementation works (936/937 tests passing)
- ✅ Matches adcp v1.2.1 design exactly
- ✅ Can migrate later when spec-compliant
- ✅ Lower risk, faster to production
- ⏱️ Timeline: Ready now

**Option B: Full Migration First**
- ⚠️ Requires 10-12 hours of code fixes
- ⚠️ High risk (touching all adapters)
- ⚠️ May discover more validation issues
- ✅ Fully spec-compliant afterward
- ⏱️ Timeline: 2-3 days

## Next Steps (Option A)

1. ✅ Keep our current oneOf implementation
2. ✅ Document spec compliance issues in backlog
3. ✅ Create tickets for Phase 1 & 2 fixes
4. ✅ Plan gradual migration over next sprint
5. ✅ Ship current implementation to production

## Next Steps (Option B)

1. Create feature branch: `fix-adcp-spec-compliance`
2. Execute Phase 1: Fix Package.status (all adapters)
3. Execute Phase 2: Fix datetime serialization
4. Execute Phase 3: Integrate adcp types
5. Full test suite validation
6. Create PR with comprehensive testing

## Lessons Learned

1. **Library validation is stricter than docs** - The adcp library enforces rules not obvious from spec reading
2. **Type compatibility requires runtime testing** - Can't assume drop-in replacement
3. **Gradual migration is safer** - All-at-once approach discovered too many issues
4. **Our tests were too lenient** - Passing tests doesn't mean spec-compliant

## References

- adcp v1.2.1: https://pypi.org/project/adcp/1.2.1/
- AdCP Spec: https://adcontextprotocol.org/schemas/v1/
- PR #23: https://github.com/adcontextprotocol/adcp-client-python/pull/23
- Test failure: `tests/unit/adapters/test_base.py::test_mock_ad_server_create_media_buy`
