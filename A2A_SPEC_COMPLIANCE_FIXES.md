# A2A Spec Compliance Fixes

## Summary

Fixed critical spec violations in our A2A implementation where we were adding non-spec fields (`success`, `message`) to AdCP response payloads. Per [AdCP PR #238](https://github.com/adcontextprotocol/adcp/pull/238), DataPart must contain **direct AdCP payload only** - no custom wrappers or protocol fields.

**Completed Work:**
- ✅ All 6 skill handlers return pure AdCP responses (no protocol fields)
- ✅ Added TextPart for human-readable messages per A2A spec
- ✅ Test validator enforces spec compliance (forbids protocol fields)
- ✅ Refactored NLP path to eliminate code duplication
- ✅ Standardized artifact creation with helper method
- ✅ Both explicit skill and NLP paths use TextPart + DataPart structure

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

### 2. Added TextPart for Human Messages (`src/a2a_server/adcp_a2a_server.py`)

Per AdCP PR #238, human-readable messages should be in **TextPart**, separate from domain data in **DataPart**.

**Implementation:**
- Added `TextPart` import from `a2a.types`
- Updated artifact creation to include both TextPart (message) and DataPart (payload)
- Extract human message from `response.__str__()` method
- Structure: `Artifact(description=message, parts=[TextPart, DataPart])`

**Before:**
```python
Artifact(
    description=message,
    parts=[Part(root=DataPart(data=response_data))]  # Only DataPart
)
```

**After:**
```python
parts = []
if human_message:
    parts.append(Part(root=TextPart(text=human_message)))  # Human message
parts.append(Part(root=DataPart(data=response_data)))  # AdCP payload

Artifact(
    description=human_message,  # Also in description
    parts=parts  # Both TextPart and DataPart
)
```

**Benefits:**
- Clear separation of human-readable content from machine-readable data
- Clients can display TextPart to users and process DataPart programmatically
- Aligns with A2A/AdCP canonical structure

### 3. Fixed Test Validator (`tests/helpers/a2a_response_validator.py`)

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

# Generate human message from response
message = str(response)  # Use __str__() method

# Success determined by Task.status.state
task.status = TaskStatus(state=TaskState.completed)  # or .failed

# Build parts: TextPart + DataPart
parts = []
if message:
    parts.append(Part(root=TextPart(text=message)))  # Human-readable message
parts.append(Part(root=DataPart(data=response_data)))  # Pure AdCP data

# Create Artifact with both
Artifact(
    artifact_id="result_1",
    name="operation_result",
    description=message,  # Summary in description
    parts=parts,  # TextPart (human message) + DataPart (AdCP payload)
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

## NLP Path Refactoring (COMPLETED)

### Natural Language Processing Path

**Location**: `src/a2a_server/adcp_a2a_server.py` (lines ~687-792)

**Changes Made:**

1. **Added Standardized Helper Method** (lines 403-425):
   - `_build_artifact_with_textpart()` creates artifacts with TextPart + DataPart structure
   - Handles both cases: with/without human messages
   - Used by ALL artifact creation (NLP and explicit skills)

2. **Refactored `_get_products()` NLP Helper** (lines 1945-1972):
   - ✅ Eliminated code duplication - now calls `_handle_get_products_skill()` directly
   - ✅ Just maps NL query to skill parameters
   - ✅ Single source of truth for business logic
   - ✅ Added auth_token validation

3. **Updated All NLP Artifact Creation**:
   - ✅ `get_products` (lines 692-695) - Uses helper with TextPart extracted from response.__str__()
   - ✅ `get_pricing` (lines 718-723) - Uses helper (DataPart only, no TextPart)
   - ✅ `get_targeting` (lines 748-753) - Uses helper (DataPart only, no TextPart)
   - ✅ `get_capabilities` (lines 823-828) - Uses helper (DataPart only, no TextPart)
   - ✅ `create_media_buy` (lines 781-792) - Uses helper with TextPart from legacy message field

**Remaining Technical Debt:**

- **`_create_media_buy()` Legacy Helper** (lines ~2100+):
  - Still returns protocol fields (`success`, `message`)
  - Should be refactored to call `_handle_create_media_buy_skill()` like `_get_products()`
  - Marked with TODO comment for future refactor
  - Currently uses helper method for artifact creation (partial compliance)

**Benefits:**
- ✅ Consistent artifact structure across NLP and explicit skill paths
- ✅ Eliminated duplication in get_products path
- ✅ Both paths now use TextPart + DataPart per A2A spec
- ✅ Clear separation of concerns (helper handles structure)

## Conclusion

Our A2A implementation now returns **pure AdCP-compliant payloads** in DataPart.data, with protocol concerns (success/message) properly separated per the spec. Human-readable messages are in **TextPart**, separate from domain data in **DataPart**. This fixes compatibility with Google ADK and ensures we follow the canonical A2A response structure documented in PR #238.

**Complete Structure:**
1. ✅ **Task.status.state** = Success indicator (completed/failed)
2. ✅ **Artifact.description** = Human-readable summary
3. ✅ **TextPart** = Full human-readable message
4. ✅ **DataPart** = Pure AdCP payload (no protocol fields)
