# A2A Spec Compliance Fixes

## Summary

Fixed critical spec violations in our A2A implementation where we were adding non-spec fields (`success`, `message`) to AdCP response payloads. Per [AdCP PR #238](https://github.com/adcontextprotocol/adcp/pull/238), DataPart must contain **direct AdCP payload only** - no custom wrappers or protocol fields.

## Root Cause

We were mixing **protocol-level concerns** (success status, human messages) with **domain data** (AdCP payloads):

```python
# ❌ WRONG - Adding non-spec fields to AdCP response
response_data = response.model_dump()
response_data["success"] = True  # Protocol field - VIOLATES SPEC
response_data["message"] = "Created successfully"  # Protocol field - VIOLATES SPEC
return response_data
```

## What the Spec Says (PR #238)

1. **DataPart MUST contain direct AdCP payload** - No custom wrappers
2. **TextPart is for human-readable messages** - Not part of data structure
3. **Status-based extraction**: Success determined by `Task.status.state` (completed/failed)
4. **"Last DataPart is authoritative"** - When multiple DataParts exist
5. **No framework wrappers**: `DataPart.data` must be pure AdCP response

### Key Quote from PR #238
> "DataPart must contain direct AdCP payload…not wrapped in custom objects. Wrappers violate protocol-agnostic design."

## Changes Made

### 1. Fixed All Skill Handlers (`src/a2a_server/adcp_a2a_server.py`)

**Handlers Fixed:**
- `_handle_get_products_skill` (line ~1371)
- `_handle_create_media_buy_skill` (lines ~1454-1458)
- `_handle_sync_creatives_skill` (lines ~1522-1527)
- `_handle_list_creatives_skill` (line ~1570)
- `_handle_list_creative_formats_skill` (line ~1787)
- `_handle_update_performance_index_skill` (lines ~1973-1978)

**Already Compliant:**
- `_handle_update_media_buy_skill` ✅
- `_handle_get_media_buy_delivery_skill` ✅

**Pattern Applied:**
```python
# ✅ CORRECT - Return pure AdCP response
if isinstance(response, dict):
    return response
else:
    return response.model_dump()
```

**Error Handling Fixed:**
```python
# Before: Custom error dict with success/message
if missing_params:
    return {"success": False, "message": "...", ...}  # ❌ WRONG

# After: Raise ServerError (proper A2A error handling)
if missing_params:
    raise ServerError(InvalidParamsError(message="..."))  # ✅ CORRECT
```

### 2. Fixed Test Validator (`tests/helpers/a2a_response_validator.py`)

**Before:**
```python
REQUIRED_FIELDS = {"success", "message"}  # ❌ Testing wrong behavior
```

**After:**
```python
FORBIDDEN_FIELDS = {"success", "message"}  # ✅ Enforces spec compliance
```

**New Validation Logic:**
- Checks for FORBIDDEN protocol fields (spec violation)
- Validates AdCP schema compliance
- Ensures responses are pure AdCP payloads

### 3. Tests Need Updating

**Files Requiring Updates:**
- `tests/integration/test_a2a_response_message_fields.py` - Tests for wrong behavior
- `tests/e2e/test_a2a_adcp_compliance.py` - May have assertions expecting message/success

**What Needs Fixing:**
- Remove assertions checking for `message`/`success` fields in DataPart.data
- Add tests validating responses DON'T have protocol fields
- Test that Task.status.state properly reflects success/failure
- Test that Artifact.description contains human-readable messages

## Why This Matters

1. **Spec Violation**: Clients expecting AdCP-compliant responses fail schema validation
2. **Google ADK Issues**: ADK expects pure AdCP responses - our mutated responses cause failures
3. **Protocol Contamination**: Mixing protocol concerns with domain data
4. **Test Confusion**: Conflicting tests - some enforce spec compliance, others enforce violations

## Correct A2A Response Structure (Per PR #238)

```python
# Handler returns pure AdCP response
response_data = response.model_dump()  # Only spec fields

# Human message goes in Artifact.description or TextPart
message = str(response)  # Use __str__() method

# Success determined by Task.status.state
task.status = TaskStatus(state=TaskState.completed)  # or .failed

# Pure data in DataPart
Artifact(
    description=message,  # Human-readable here
    parts=[Part(root=DataPart(data=response_data))]  # Pure AdCP data
)
```

## Impact Assessment

**Affected Operations:**
- All 8+ AdCP skill handlers (create_media_buy, sync_creatives, etc.)
- All integration tests using A2A response validator
- E2E tests checking response structure

**Breaking Changes:**
- Responses no longer contain `success`/`message` fields in DataPart.data
- Tests expecting these fields will fail
- Clients must use Task.status.state for success detection
- Human messages must come from Artifact.description or TextPart

## Next Steps

1. ✅ **Stage 1 Complete**: Skill handlers return pure AdCP responses
2. ✅ **Stage 2 Complete**: Test validator enforces spec compliance
3. **Stage 3 Pending**: Update integration tests for correct behavior
4. **Stage 4 Pending**: Add tests validating proper A2A structure (Task.status, Artifact.description)
5. **Stage 5 Pending**: Run full test suite to verify compliance

## References

- **AdCP PR #238**: "Document canonical A2A response structure"
- **AdCP Spec**: https://adcontextprotocol.org/docs/
- **Issue**: Google ADK compatibility (strange behaviors with non-compliant responses)

## Testing Recommendations

### What to Test

1. **DataPart Purity**:
   ```python
   # ✅ Validate no protocol fields in data
   assert "success" not in data_part.data
   assert "message" not in data_part.data
   ```

2. **Schema Validation**:
   ```python
   # ✅ DataPart.data validates against AdCP schema
   AdCPResponseModel(**data_part.data)  # Should not raise
   ```

3. **Protocol Fields Location**:
   ```python
   # ✅ Success in Task.status.state
   assert task.status.state == TaskState.completed

   # ✅ Message in Artifact.description
   assert artifact.description == "Media buy created successfully"
   ```

### Integration Test Pattern

```python
async def test_create_media_buy_spec_compliance():
    """Test create_media_buy returns spec-compliant A2A response."""
    # Execute skill
    result = await handler._handle_create_media_buy_skill(params, token)

    # ✅ Validate no protocol fields
    assert "success" not in result
    assert "message" not in result

    # ✅ Validate AdCP schema compliance
    from adcp.types.aliases import CreateMediaBuySuccessResponse
    CreateMediaBuySuccessResponse(**result)  # Should validate

    # ✅ Check required AdCP fields present
    assert "media_buy_id" in result or "buyer_ref" in result
```

## Conclusion

Our A2A implementation now returns **pure AdCP-compliant payloads** in DataPart.data, with protocol concerns (success/message) properly separated per the spec. This fixes compatibility with Google ADK and ensures we follow the canonical A2A response structure documented in PR #238.
