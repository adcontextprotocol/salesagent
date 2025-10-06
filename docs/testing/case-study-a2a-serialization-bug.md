# Case Study: A2A create_media_buy Serialization Bug

## Summary

A serialization bug in the A2A `create_media_buy` endpoint went undetected until production testing, despite having integration tests. This case study documents the bug, why tests didn't catch it, and improvements implemented.

## The Bug

**Error**: `'dict' object has no attribute 'model_dump'`

**Location**: `src/a2a_server/adcp_a2a_server.py` line 1053

**Code**:
```python
# WRONG: Trying to call .model_dump() on dicts
"packages": [package.model_dump() for package in response.packages]

# CORRECT: Packages are already dicts
"packages": response.packages
```

**Root Cause**: `CreateMediaBuyResponse.packages` is defined as `list[dict[str, Any]]`, not a list of Pydantic models.

## Why Tests Didn't Catch It

### 1. Over-Mocking in Integration Tests

**Original Test** (`tests/integration/test_a2a_skill_invocation.py:350-362`):
```python
# ❌ Mocked the adapter completely
with patch("src.core.main.get_adapter") as mock_get_adapter:
    mock_adapter = MagicMock()
    mock_adapter.create_media_buy.return_value = {
        "media_buy_id": "mb_12345",
        "status": "active",
    }
    mock_get_adapter.return_value = mock_adapter
```

**Problem**: This bypassed:
- The real `_create_media_buy_impl` function
- The real `CreateMediaBuyResponse` object creation
- The buggy A2A serialization code

**Result**: Test passed even though production code was broken.

### 2. E2E Tests Not Blocking CI

The e2e test `tests/e2e/test_a2a_adcp_compliance.py::test_explicit_skill_create_media_buy` would have caught this bug because it:
- Makes real HTTP requests to the A2A server
- Exercises the full code path including serialization
- Uses real response objects

**However**: CI configuration (`.github/workflows/test.yml:343`) had:
```yaml
continue-on-error: true  # E2E tests may be flaky
```

**Result**: E2E test failures didn't block CI, so the bug wasn't caught before merge.

## Testing Anti-Patterns Demonstrated

This bug is a textbook example of anti-patterns documented in `docs/testing/`:

### Anti-Pattern #1: Mocking Internal Code
```python
# ❌ WRONG: Mocking our own adapter
patch("src.core.main.get_adapter")

# ✅ CORRECT: Use real mock adapter from database
# (Only mock external dependencies like GAM API)
```

**Guideline**: "Mock only external dependencies, not our own code"

### Anti-Pattern #2: Testing Implementation Details
The original test verified task creation and artifact structure, but didn't verify the actual response serialization:
```python
# ❌ Insufficient: Only checks structure
assert len(result.artifacts) == 1
assert result.artifacts[0].name == "create_media_buy_result"

# ✅ Better: Also verify serialization
assert "packages" in artifact_data
assert isinstance(artifact_data["packages"], list)
```

### Anti-Pattern #3: Ignoring Test Failures
Having `continue-on-error: true` for e2e tests meant we treated them as "nice to have" instead of "must pass."

## Improvements Implemented

### 1. Reduced Mocking in Integration Test

**File**: `tests/integration/test_a2a_skill_invocation.py:339-388`

**Before**: 3 mocks (auth + tenant + adapter)
**After**: 2 mocks (only auth + tenant)

**New Test**:
```python
async def test_explicit_skill_create_media_buy(...):
    """NOTE: This test now uses the REAL mock adapter and code paths,
    only mocking authentication. This ensures we catch serialization bugs."""

    # Mock ONLY authentication - use real adapter and implementation
    with (
        patch("...get_principal_from_token") as mock_get_principal,
        patch("...get_current_tenant") as mock_get_tenant,
    ):
        # Process the message - executes REAL _create_media_buy_impl
        result = await handler.on_message_send(params)

        # Verify packages are properly serialized
        assert "packages" in artifact_data
        assert isinstance(artifact_data["packages"], list)
```

**Impact**: This test now exercises the real serialization code and would have caught the bug.

### 2. Made E2E Tests Blocking in CI

**File**: `.github/workflows/test.yml`

**Changes**:
- Removed `continue-on-error: true` from e2e tests (line 343)
- Added e2e-tests to test-summary job dependencies (line 387)
- Updated summary check to include e2e test results (lines 393-395)

**Impact**: E2E test failures now block CI, catching integration bugs earlier.

### 3. Added Serialization Verification

Added explicit assertions that would have caught this specific bug:
```python
# Verify packages are properly serialized (this would have caught the bug!)
assert "packages" in artifact_data
assert isinstance(artifact_data["packages"], list)
```

## Testing Best Practices

Based on this case study, follow these principles:

### ✅ DO

1. **Test at boundaries**: For API handlers, test HTTP request/response, not internal functions
2. **Use real implementations**: Use the actual mock adapter, not MagicMock
3. **Mock only external systems**: GAM API, external services, not our own code
4. **Verify serialization**: Check data types and structure, not just presence
5. **Make critical tests blocking**: If a test matters, it should block CI when it fails

### ❌ DON'T

1. **Over-mock**: Don't mock internal functions that are part of the code path under test
2. **Ignore test failures**: `continue-on-error: true` should be rare and justified
3. **Test implementation details**: Focus on behavior and contracts, not internal structure
4. **Skip integration tests**: They catch bugs that unit tests with mocks cannot

## Metrics

**Test Coverage Impact**:
- Mocks reduced: 3 → 2 (33% reduction)
- Code paths tested: Added real `_create_media_buy_impl` execution
- Bug detection: Would now catch this bug class

**CI Reliability**:
- E2E tests now blocking (was optional)
- Test pyramid now enforced at all levels

## Related Documentation

- [Testing Philosophy](./README.md)
- [Integration Testing Best Practices](./integration-testing.md)
- [Mocking Guidelines](./mocking-guidelines.md)
- [Pre-commit Hooks](../../.pre-commit-hooks.md)

## Lessons Learned

1. **Over-mocking hides bugs**: The more you mock, the less confidence your tests provide
2. **Integration tests need real code**: Tests that bypass implementation can't catch implementation bugs
3. **E2E tests are critical**: They're the only tests that exercise the full system
4. **Test enforcement matters**: Tests that don't block CI don't prevent bugs

## Prevention

To prevent similar bugs:

1. **Run pre-commit hook**: `pre-commit run no-excessive-mocking --all-files`
2. **Check mock count**: Max 10 mocks per test file
3. **Review integration tests**: Ask "does this test real code paths?"
4. **Enforce e2e tests**: Keep them fast and blocking in CI
5. **Test serialization**: Always verify response structure and types

## References

- **Bug Fix PR**: #282
- **Testing Improvements PR**: #[TODO]
- **Related Issues**: Testing anti-patterns, over-mocking
