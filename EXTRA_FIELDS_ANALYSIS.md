# Extra Fields Analysis: AdCP Response Schema Compliance

**Date:** 2025-10-26
**Issue:** UserWarnings triggered by extra fields in AdCP response models that are not in the official specification

## Executive Summary

5 response models contain fields NOT in the official AdCP v2.2.0 specification:

| Response Model | Extra Fields | AdCP Spec | Status | Recommendation |
|---|---|---|---|---|
| **ActivateSignalResponse** | `task_id`, `status` | ❌ Not in spec | ⚠️ **BREAKING** | Keep (protocol layer) |
| **ListCreativesResponse** | `context_id` | ❌ Not in spec | ⚠️ **BREAKING** | Keep (internal state) |
| **CreateMediaBuyResponse** | `workflow_step_id` | ❌ Not in spec | ✅ Safe to hide | Already excluded via `model_dump()` |
| **GetProductsResponse** | `status` | ❌ Not in spec | ✅ Safe to remove | Unused in code |
| **ListCreativeFormatsResponse** | `status` | ❌ Not in spec | ✅ Safe to remove | Unused in code |

## Detailed Analysis

### 1. ActivateSignalResponse - `task_id` and `status`

**Location:** `src/core/schema_adapters.py:718-728`

**Current Implementation:**
```python
class ActivateSignalResponse(AdCPBaseModel):
    task_id: str = Field(..., description="Unique identifier for tracking")
    status: str = Field(..., description="Current status (pending/processing/deployed/failed)")
    decisioning_platform_segment_id: str | None = None
    estimated_activation_duration_minutes: float | None = None
    deployed_at: str | None = None
    errors: list[Any] | None = None
```

**Official AdCP Spec** (`src/core/schemas_generated/_schemas_v1_signals_activate_signal_response_json.py:29-45`):
```python
class ActivateSignalResponse(BaseModel):
    decisioning_platform_segment_id: str | None = None  # ✅ In spec
    estimated_activation_duration_minutes: float | None = None  # ✅ In spec
    deployed_at: AwareDatetime | None = None  # ✅ In spec
    errors: list[Error] | None = None  # ✅ In spec
    # ❌ task_id NOT in spec
    # ❌ status NOT in spec
```

**Usage Analysis:**
```python
# src/core/tools/signals.py:257-270
return ActivateSignalResponse(
    task_id=task_id,  # ❌ Extra field
    status=status,    # ❌ Extra field
    decisioning_platform_segment_id=platform_id,
    estimated_activation_duration_minutes=duration,
)
```

**Impact:**
- **HIGH** - These fields are actively used for async task tracking
- `task_id` is generated and returned to clients for tracking activation progress
- `status` indicates activation state: `pending`, `processing`, `deployed`, `failed`
- Used in both MCP and A2A protocol layers

**Recommendation:** **KEEP - Protocol Layer Fields**
- These fields are part of the protocol envelope pattern (similar to AdCP PR #113)
- They should be added to AdCP spec OR moved to `ProtocolEnvelope` wrapper
- **Option 1 (Preferred):** File issue with AdCP maintainers to add these fields to spec
- **Option 2:** Move to `ProtocolEnvelope` and exclude from AdCP response via `model_dump()`

**Action:** Document as intentional deviation with rationale

---

### 2. ListCreativesResponse - `context_id`

**Location:** `src/core/schema_adapters.py:753-761`

**Current Implementation:**
```python
class ListCreativesResponse(AdCPBaseModel):
    query_summary: Any = Field(..., description="Summary of the query")
    pagination: Any = Field(..., description="Pagination information")
    creatives: list[Any] = Field(..., description="Array of creative assets")
    context_id: str | None = None  # ❌ Not in spec
    format_summary: dict[str, int] | None = None  # ✅ In spec
    status_summary: dict[str, int] | None = None  # ❌ Not in spec (but acceptable)
```

**Official AdCP Spec** (`src/core/schemas_generated/_schemas_v1_media_buy_list_creatives_response_json.py:777-785`):
```python
class ListCreativesResponse(BaseModel):
    query_summary: QuerySummary  # ✅ In spec
    pagination: Pagination  # ✅ In spec
    creatives: list[Creative]  # ✅ In spec
    format_summary: dict[str, int] | None = None  # ✅ In spec
    status_summary: StatusSummary | None = None  # ✅ In spec (different structure)
    # ❌ context_id NOT in spec
```

**Usage Analysis:**
```python
# src/core/tools/creatives.py:422-430, 457, 486 (generative creative context tracking)
existing_context_id = None
if existing_creative.data:
    existing_context_id = existing_creative.data.get("generative_context_id")

context_id = creative.get("context_id") or existing_context_id

# Used for generative creative refinement (Gemini API context)
build_result = build_creative(
    gemini_api_key=gemini_api_key,
    context_id=context_id,  # Links conversation history for refinement
    finalize=creative.get("approved", False),
)

data["generative_context_id"] = build_result.get("context_id")
```

**Impact:**
- **MEDIUM** - Used internally for generative creative workflow state
- Tracks Gemini API conversation context for creative refinement
- NOT returned in response (stored in database `Creative.data` field)
- Field exists in response schema but is never populated from tool logic

**Recommendation:** **REMOVE from Schema - Internal State Only**
- This is internal workflow state, not AdCP protocol data
- Already stored in `Creative.data.generative_context_id` (database field)
- Response schema should not include this field
- Move to internal creative management layer

**Action:** Remove `context_id` field from `ListCreativesResponse` schema

---

### 3. CreateMediaBuyResponse - `workflow_step_id`

**Location:** `src/core/schema_adapters.py:517-567`

**Current Implementation:**
```python
class CreateMediaBuyResponse(AdCPBaseModel):
    buyer_ref: str = Field(..., description="Buyer's reference identifier")
    media_buy_id: str | None = None
    creative_deadline: Any | None = None
    packages: list[Any] | None = Field(default_factory=list)
    errors: list[Any] | None = None
    workflow_step_id: str | None = None  # ❌ Not in spec, BUT already excluded

    def model_dump(self, **kwargs):
        """AdCP-compliant dump (excludes internal fields)."""
        exclude = kwargs.get("exclude", set())
        if isinstance(exclude, set):
            exclude.add("workflow_step_id")  # ✅ Already excluded from AdCP responses
            kwargs["exclude"] = exclude
        return super().model_dump(**kwargs)

    def model_dump_internal(self, **kwargs):
        """Dump including internal fields for database storage."""
        kwargs.pop("exclude", None)
        return super().model_dump(**kwargs)
```

**Usage Analysis:**
```python
# src/core/tools/media_buy_create.py:899, 1037, 1186
return CreateMediaBuyResponse(
    buyer_ref=req.buyer_ref,
    media_buy_id=media_buy_id,
    packages=packages,
    workflow_step_id=step.step_id,  # ✅ Used for approval tracking
)

# Later stored in database via model_dump_internal()
# Never sent to clients (excluded via model_dump())
```

**Impact:**
- **NONE** - Already handled correctly
- Field is explicitly excluded from AdCP responses via custom `model_dump()`
- Only included in internal storage via `model_dump_internal()`
- Used for workflow approval tracking

**Recommendation:** **KEEP - Already Implemented Correctly**
- This field follows the documented pattern in schema_adapters.py
- Internal fields are excluded from protocol responses
- Database storage includes internal fields
- No changes needed

**Action:** None - working as designed

---

### 4. GetProductsResponse - `status`

**Location:** `src/core/schema_adapters.py:146-164`

**Current Implementation:**
```python
class GetProductsResponse(AdCPBaseModel):
    products: list[Any] = Field(..., description="List of matching products")
    status: str | None = Field(None, description="Response status")  # ❌ Not in spec
    errors: list[Any] | None = Field(None, description="Task-specific errors")
```

**Official AdCP Spec:** No `status` field exists in official schema

**Usage Analysis:**
```python
# src/core/tools/products.py:502 (ONLY usage)
return GetProductsResponse(
    products=modified_products,
    status=status  # ⚠️ Unused by clients, internal-only
)
```

**Impact:**
- **NONE** - Field is set but never read
- Not used in MCP or A2A protocol layers
- Not documented in API
- Appears to be vestigial code

**Recommendation:** **REMOVE - Unused Field**
- Remove `status` field from `GetProductsResponse` schema
- Remove `status` parameter from return statement in `products.py:502`
- Field provides no value and violates AdCP spec

**Action:** Safe to remove immediately

---

### 5. ListCreativeFormatsResponse - `status`

**Location:** `src/core/schema_adapters.py:358-376`

**Current Implementation:**
```python
class ListCreativeFormatsResponse(AdCPBaseModel):
    formats: list[Any] = Field(..., description="Full format definitions per AdCP spec")
    status: str | None = Field("completed", description="Task status")  # ❌ Not in spec
    creative_agents: list[Any] | None = Field(None, description="Creative agents...")
    errors: list[Any] | None = Field(None, description="Task-specific errors")
```

**Official AdCP Spec:** No `status` field exists in official schema

**Usage Analysis:**
```python
# src/core/tools/creative_formats.py:123 (ONLY usage)
response = ListCreativeFormatsResponse(
    formats=formats,
    status=status  # ⚠️ Unused by clients, defaults to "completed"
)
```

**Impact:**
- **NONE** - Field is set but never read
- Always defaults to `"completed"`
- Not used in MCP or A2A protocol layers
- Appears to be vestigial code from async task pattern

**Recommendation:** **REMOVE - Unused Field**
- Remove `status` field from `ListCreativeFormatsResponse` schema
- Remove `status` parameter from return statement in `creative_formats.py:123`
- Field provides no value and violates AdCP spec

**Action:** Safe to remove immediately

---

## Summary of Recommendations

### Immediate Actions (Safe to Remove)

1. **Remove `status` from GetProductsResponse**
   - File: `src/core/schema_adapters.py:164`
   - Impact: None (unused)
   - Risk: Low

2. **Remove `status` from ListCreativeFormatsResponse**
   - File: `src/core/schema_adapters.py:376`
   - Impact: None (unused)
   - Risk: Low

3. **Remove `context_id` from ListCreativesResponse**
   - File: `src/core/schema_adapters.py:761`
   - Impact: None (internal state, not returned)
   - Risk: Low

### Defer/Document (Breaking Changes)

4. **Keep `task_id` and `status` in ActivateSignalResponse**
   - File: `src/core/schema_adapters.py:723-724`
   - Rationale: Required for async task tracking
   - Action: Document as intentional deviation OR file AdCP spec issue
   - Risk: High (breaking change to remove)

5. **Keep `workflow_step_id` in CreateMediaBuyResponse**
   - File: `src/core/schema_adapters.py:547`
   - Status: Already handled correctly (excluded from AdCP responses)
   - Action: None needed
   - Risk: None

---

## Implementation Plan

### Phase 1: Safe Removals (Immediate)

**Step 1:** Remove unused `status` fields
```python
# File: src/core/schema_adapters.py

# GetProductsResponse (line 164)
- status: str | None = Field(None, description="Response status")

# ListCreativeFormatsResponse (line 376)
- status: str | None = Field("completed", description="Task status")
```

**Step 2:** Update tool implementations
```python
# File: src/core/tools/products.py (line 502)
- return GetProductsResponse(products=modified_products, status=status)
+ return GetProductsResponse(products=modified_products)

# File: src/core/tools/creative_formats.py (line 123)
- response = ListCreativeFormatsResponse(formats=formats, status=status)
+ response = ListCreativeFormatsResponse(formats=formats)
```

**Step 3:** Remove `context_id` from ListCreativesResponse
```python
# File: src/core/schema_adapters.py (line 761)
- context_id: str | None = None
```

### Phase 2: Documentation (Deferred)

**Document ActivateSignalResponse deviation:**
```markdown
# Known AdCP Spec Deviations

## ActivateSignalResponse Extra Fields

**Fields:** `task_id`, `status`
**Rationale:** Required for async signal activation tracking
**Status:** Intentional deviation (protocol layer fields)
**Future:** File issue with AdCP maintainers to add to spec
```

---

## Testing Impact

### Tests to Update

1. **Unit tests using these fields**
   - Search: `grep -r "status.*GetProductsResponse" tests/`
   - Search: `grep -r "status.*ListCreativeFormatsResponse" tests/`
   - Update assertions to remove `status` field checks

2. **AdCP contract tests**
   - `tests/unit/test_adcp_contract.py` may need updates
   - Verify no tests explicitly check for removed fields

3. **Integration tests**
   - Verify no integration tests depend on removed fields
   - Update any tests that construct responses with these fields

### No Breaking Changes Expected

- All removed fields are unused or internal-only
- `workflow_step_id` already excluded from AdCP responses
- `ActivateSignalResponse` changes deferred (breaking)

---

## Future Considerations

### AdCP Spec Evolution

1. **File issues for missing fields:**
   - `ActivateSignalResponse`: Add `task_id` and `status` for async tracking
   - Rationale: Common pattern across async operations

2. **Consider ProtocolEnvelope pattern:**
   - Move protocol-level fields (`task_id`, `status`, `context_id`) to wrapper
   - Keep domain responses pure (only AdCP spec fields)
   - Follow pattern from AdCP PR #113

3. **Schema generation improvements:**
   - Add validation step: compare adapter schemas to generated schemas
   - Fail CI if extra fields detected (opt-in initially)
   - Document intentional deviations in YAML/JSON

---

## Conclusion

**Total Extra Fields:** 5 models with 6 extra fields

**Safe to Remove:** 3 fields (60%)
- `GetProductsResponse.status`
- `ListCreativeFormatsResponse.status`
- `ListCreativesResponse.context_id`

**Keep (Already Handled):** 1 field (20%)
- `CreateMediaBuyResponse.workflow_step_id` ✅

**Keep (Breaking):** 2 fields (40%)
- `ActivateSignalResponse.task_id`
- `ActivateSignalResponse.status`

**Next Steps:**
1. Implement Phase 1 removals (safe, immediate)
2. Document ActivateSignalResponse deviation
3. Consider filing AdCP spec issues for missing fields
4. Add CI validation for future schema compliance
