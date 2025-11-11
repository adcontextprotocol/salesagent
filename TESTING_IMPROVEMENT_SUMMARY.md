# Testing Gap Analysis: sync_creatives Response Validation

## The Bug That Wasn't Caught

### What Happened
Users reported validation failures with `sync_creatives`:
- **JavaScript client**: `"agentConfigs is not iterable"`
- **Python client**: `"Data doesn't match any Union variant"`

### Root Cause
The `SyncCreativeResult` schema included internal fields (`status`, `review_feedback`) that:
1. Are NOT in the official AdCP specification
2. Violated the `"additionalProperties": false` constraint in the generated schema
3. Caused client-side validation to fail when parsing responses

### Why Tests Didn't Catch It

Our existing test (`test_sync_creatives_response_adcp_compliance` in `tests/unit/test_adcp_contract.py`):

```python
def test_sync_creatives_response_adcp_compliance(self):
    response = SyncCreativesResponse(
        creatives=[
            SyncCreativeResult(
                creative_id="creative_123",
                action="created",
                status="approved",  # ⚠️ This field violates the spec!
            )
        ]
    )

    adcp_response = response.model_dump()

    # ❌ Only checks that fields exist, doesn't validate schema
    assert "creatives" in adcp_response
    assert "creative_id" in adcp_response["creatives"][0]
```

**Problem**: The test only checks for field **presence**, not field **validity**.

## The Fix

### Code Changes (commit f5bd7b8a)

Added `model_dump()` overrides to exclude internal fields:

```python
class SyncCreativeResult(BaseModel):
    # ... fields ...

    def model_dump(self, **kwargs):
        """Exclude internal fields for AdCP compliance."""
        exclude = kwargs.get("exclude", set())
        if isinstance(exclude, set):
            exclude.update({"status", "review_feedback"})
            kwargs["exclude"] = exclude
        # ... rest of implementation
```

### Test Improvements (commit e8c734ba)

Created `test_sync_creatives_generated_schema_validation.py` that:

1. **Validates against the actual generated schema**:
   ```python
   from src.core.schemas_generated._schemas_v1_media_buy_sync_creatives_response_json import (
       Creative as GeneratedCreative,
       SyncCreativesResponse1
   )

   # This will fail if extra fields are present
   creative_obj = GeneratedCreative(**creative_data)
   ```

2. **Tests with internal fields** (as the implementation uses them):
   ```python
   result = SyncCreativeResult(
       creative_id="test",
       action="created",
       status="pending_review",  # Internal field
       review_feedback="AI approved",  # Internal field
   )
   ```

3. **Proves the bug would be caught**:
   - Without the fix: `ValidationError: Extra inputs are not permitted: status, review_feedback`
   - With the fix: ✅ All tests pass

## Testing Best Practices Going Forward

### 1. Always Validate Against Generated Schemas

For ANY response that goes to clients:

```python
def test_my_response_validates_against_generated_schema():
    """Ensure response matches the schema clients use."""
    from src.core.schemas_generated._schemas_v1_... import GeneratedResponse

    response = MyResponse(...)
    response_dict = response.model_dump()

    # This catches "additionalProperties": false violations
    generated_obj = GeneratedResponse(**response_dict)
    assert generated_obj is not None
```

### 2. Test Pattern for All AdCP Responses

```python
# ❌ BAD - Only checks field presence
assert "field" in response_dict

# ✅ GOOD - Validates against schema
GeneratedSchema(**response_dict)  # Will raise ValidationError if invalid
```

### 3. When to Add These Tests

**Always add generated schema validation for:**
- New response models
- Responses with internal fields
- Responses with complex nested structures
- Responses going to external clients

**Especially important when:**
- The spec has `"additionalProperties": false`
- You're using `oneOf`/`anyOf` unions
- You have fields marked as "internal" or "for database only"

## Checklist for Future Response Models

When creating/modifying response models:

- [ ] Check official AdCP spec for allowed fields
- [ ] Mark internal fields clearly in docstrings
- [ ] Add `model_dump()` override to exclude internal fields
- [ ] Write test that validates against generated schema
- [ ] Test with both minimal and full field sets
- [ ] Verify empty lists/None values are excluded properly

## Files Changed

### Production Code
- `src/core/schemas.py` - Added `model_dump()` overrides

### Tests
- `tests/unit/test_sync_creatives_generated_schema_validation.py` - New validation tests
- `tests/unit/test_adcp_contract.py` - Existing (needs similar improvements for other responses)

### Schema Files (Not Committed)
Multiple schema files were regenerated but not committed because:
1. They represent a broader schema update (not specific to this bug fix)
2. Schema updates should be in a separate PR with full validation
3. Our fix works with both old and new schema versions

## Recommendations

1. **Audit other AdCP response tests**: Check if they validate against generated schemas
2. **Add pre-commit hook**: Ensure all response models have validation tests
3. **Document pattern**: Add to CLAUDE.md testing guidelines
4. **Schema CI check**: Warn when generated schemas differ from main branch

## Related Issues

- User report: JS client "agentConfigs is not iterable"
- User report: Python client "Data doesn't match any Union variant"
- AdCP PR #113: Response schema refactoring
- Official spec: `/schemas/v1/media-buy/sync-creatives-response.json`
