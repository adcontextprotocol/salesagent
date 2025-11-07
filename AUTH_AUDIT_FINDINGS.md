# Authentication Audit Findings - 2025-11-07

## Executive Summary

A critical authentication gap was discovered in `sync_creatives` where missing/invalid auth headers caused NOT NULL database constraint violations. Investigation revealed this slipped through testing because **all integration tests provide mock authentication**, never testing the unauthenticated code path.

## Root Cause Analysis

### The Bug
`sync_creatives` would:
1. Call `get_principal_id_from_context(context)` → returns `None` if auth missing/invalid
2. Continue processing without checking if `principal_id` is `None`
3. Attempt database insert with `principal_id=None`
4. Fail with: `(psycopg2.errors.NotNullViolation) null value in column "principal_id"`

### Why Tests Didn't Catch It

**Integration tests ALWAYS provide authentication:**

```python
class MockContext:
    """Mock FastMCP Context for testing."""
    def __init__(self, auth_token="test-token-preserve"):
        self.meta = {"headers": {"x-adcp-auth": auth_token}}
```

**Key insight:** Tests focus on happy paths with valid auth, never testing auth failure scenarios.

## Comprehensive Tool Authentication Audit

### ✅ Tools with PROPER Auth Checks

| Tool | File | Auth Pattern | Status |
|------|------|--------------|--------|
| `create_media_buy` | `media_buy_create.py:1266` | `if principal_id is None: raise ToolError` | ✅ SECURE |
| `get_media_buy_delivery` | `media_buy_delivery.py:59` | `if not principal_id: raise ToolError` | ✅ SECURE |
| `update_performance_index` | `performance.py:57` | `if principal_id is None: raise ToolError` | ✅ SECURE |
| `activate_signal` | `signals.py` | Calls `_get_principal_id_from_context` with check | ✅ SECURE |

### ⚠️ Tools with WEAK Auth Checks

| Tool | File | Issue | Risk Level |
|------|------|-------|-----------|
| `update_media_buy` | `media_buy_update.py:82` | Uses `assert` instead of `raise ToolError` | ⚠️ MEDIUM |

**Problem with `update_media_buy`:**
```python
# Line 79-82
if media_buy.principal_id != principal_id:
    # ...
    assert principal_id is not None, "principal_id should be set at this point"
```

- **Issue**: `assert` statements are removed when Python runs with `-O` (optimize flag)
- **Risk**: In production with optimization, this check disappears
- **Fix**: Replace with explicit `if not principal_id: raise ToolError(...)`

### ✅ Discovery Endpoints (Optional Auth)

These endpoints are designed to work without authentication:

| Tool | Purpose | Auth Behavior |
|------|---------|---------------|
| `get_products` | Product discovery | Optional auth, works without |
| `list_creative_formats` | Format discovery | Optional auth, works without |
| `list_authorized_properties` | Property discovery | Optional auth, works without |

## Fixed Issues

### 1. `sync_creatives` - **FIXED ✅**
- **Commit**: `ab3121c8` - Added explicit auth check
- **Test**: `test_sync_creatives_auth.py` - Validates error on missing auth

```python
# BEFORE (line 85):
principal_id = get_principal_id_from_context(context)
# [no check, continues to database insert]

# AFTER (lines 85-92):
principal_id = get_principal_id_from_context(context)
if not principal_id:
    raise ToolError(
        "Authentication required: Missing or invalid x-adcp-auth header. "
        "Creative sync requires authentication to associate creatives with an advertiser principal."
    )
```

### 2. `list_creatives` - **Already Protected ✅**
- Has check at line 1791-1792: `if not principal_id: raise ToolError`

## Remaining Work

### 1. Fix `update_media_buy` Assert (HIGH PRIORITY)

**Current code (media_buy_update.py:82):**
```python
assert principal_id is not None, "principal_id should be set at this point"
```

**Should be:**
```python
if not principal_id:
    raise ToolError("Authentication required: principal_id not found in context")
```

**Why this matters:**
- Asserts are disabled with `python -O` (production optimization)
- This is a security check, not a developer assertion
- Could allow unauthorized media buy updates in optimized production

### 2. Add Negative Auth Tests for ALL Tools

**Current gap:** Integration tests only test authenticated paths.

**Needed tests:**
```python
def test_<tool>_requires_authentication():
    """Verify <tool> raises ToolError when called without auth."""
    # Call tool with context=None (no auth)
    with pytest.raises(ToolError) as exc_info:
        <tool>_impl(..., context=None)

    assert "Authentication required" in str(exc_info.value)
    assert "x-adcp-auth" in str(exc_info.value)
```

**Tools needing negative auth tests:**
- [x] `sync_creatives` - Added in `test_sync_creatives_auth.py`
- [ ] `create_media_buy`
- [ ] `update_media_buy`
- [ ] `get_media_buy_delivery`
- [ ] `update_performance_index`
- [ ] `list_creatives`
- [ ] `get_signals`
- [ ] `activate_signal`

### 3. Pre-commit Hook for Auth Checks

Add hook to detect missing auth checks in new `_impl` functions:

```python
# Check for patterns like:
# - principal_id = get_principal_id_from_context(context)
# - Followed by if not principal_id: raise ToolError
```

## Recommendations

### Immediate (This Week)

1. ✅ **DONE**: Fix `sync_creatives` auth check
2. ✅ **DONE**: Add `test_sync_creatives_auth.py`
3. **TODO**: Fix `update_media_buy` assert → explicit check
4. **TODO**: Add negative auth tests for all authenticated tools

### Short-term (Next Sprint)

1. Create `tests/unit/test_auth_requirements.py` with comprehensive auth tests
2. Add pre-commit hook to enforce auth check patterns
3. Document authentication requirements in `docs/security.md`

### Long-term (Next Quarter)

1. Consider decorator pattern for auth requirements:
   ```python
   @requires_auth
   def _sync_creatives_impl(...):
       # Auth check happens in decorator
   ```

2. Add integration tests that explicitly test unauthenticated paths
3. Add E2E smoke tests that call tools without auth headers

## Testing Principles Learned

### ❌ What We Were Doing Wrong

```python
# ALL integration tests looked like this:
def test_sync_creatives(...):
    context = MockContext(auth_token="test-token")  # ALWAYS has auth
    sync_creatives_raw(..., context=context)
```

**Problem:** Never tested the unauthenticated code path!

### ✅ What We Should Do

```python
# Test BOTH paths:
def test_sync_creatives_with_auth(...):
    context = MockContext(auth_token="valid-token")
    result = sync_creatives_raw(..., context=context)
    assert result.success

def test_sync_creatives_without_auth(...):
    context = None  # No auth
    with pytest.raises(ToolError) as exc:
        sync_creatives_raw(..., context=context)
    assert "Authentication required" in str(exc.value)

def test_sync_creatives_with_invalid_auth(...):
    context = MockContext(auth_token="invalid-token")
    with pytest.raises(ToolError) as exc:
        sync_creatives_raw(..., context=context)
    assert "Authentication" in str(exc.value)
```

## Impact Assessment

### Severity: **HIGH**
- User-facing error: Database constraint violation (confusing)
- Security implication: Tools attempted to process requests without authentication
- Data integrity: Could have created orphaned records if auth was optional

### Affected Systems
- MCP server endpoints (when called without x-adcp-auth header)
- A2A server endpoints (when principal_id not set in ToolContext)

### Mitigating Factors
- Database constraints prevented data corruption
- No security breach (failed before processing)
- User-facing error message was unclear but safe

## Lessons Learned

1. **Test negative paths explicitly** - Don't just test happy paths
2. **Auth failures are a feature** - Missing auth should fail gracefully with clear errors
3. **Database constraints are last resort** - Catch errors before database layer
4. **Mocks hide bugs** - Be careful about what your mocks assume
5. **Integration tests need edge cases** - Not just happy path validation

## Related Files

- Implementation: `src/core/tools/creatives.py`
- Auth helpers: `src/core/helpers/context_helpers.py`
- Auth logic: `src/core/auth.py`
- Tests: `tests/unit/test_sync_creatives_auth.py`
- Integration tests: `tests/integration/test_creative_sync_data_preservation.py`

---

**Document Author:** Claude Code
**Date:** 2025-11-07
**Branch:** `fix-sync-creatives-principal-id`
