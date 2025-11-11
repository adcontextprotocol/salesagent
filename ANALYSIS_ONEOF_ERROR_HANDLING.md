# Analysis: AdCP PR #186 - OneOf Error Handling

## Executive Summary

**Verdict: This is a POSITIVE change that will significantly improve our implementation, with moderate migration effort required.**

The proposed `oneOf` discriminator pattern solves a critical safety issue in AdCP by enforcing atomic operation semantics. This change is **highly beneficial** for TypeScript schema generation and will make our error handling more robust.

---

## The Problem Being Solved

### Current State (Dangerous)
Our current schemas allow **partial success** scenarios where:
- A media buy is created (`media_buy_id` is set)
- BUT critical constraints are silently dropped (e.g., dayparting)
- AND the response looks "successful" because `media_buy_id` exists

**Real-world risk:**
```python
# Buyer requests: US targeting + Tuesday-only dayparting
request = CreateMediaBuyRequest(
    buyer_ref="campaign_123",
    packages=[Package(
        targeting=Targeting(geo_locations=["US"], day_of_week=[2]),  # Tuesday only
        # ...
    )]
)

# Current schema allows this DANGEROUS response:
response = CreateMediaBuyResponse(
    media_buy_id="mb_789",  # ✅ Created!
    buyer_ref="campaign_123",
    packages=[...]  # ⚠️ But dayparting was silently dropped!
)
# No errors array, looks successful, but constraint missing = $$$ overspend
```

### Proposed State (Safe)
With `oneOf` discriminators:
```json
{
  "oneOf": [
    {
      "description": "Success: ALL constraints fulfilled",
      "required": ["media_buy_id", "buyer_ref", "packages"],
      "not": {"required": ["errors"]}
    },
    {
      "description": "Error: operation failed",
      "required": ["errors"],
      "not": {"required": ["media_buy_id"]}
    }
  ]
}
```

**Result:** Operations either **succeed completely** or **fail completely**. No middle ground.

---

## Impact on Our Codebase

### 1. Current Schema Implementation (Pydantic)

**Our current implementation ALREADY supports both patterns:**

```python
class CreateMediaBuyResponse(AdCPBaseModel):
    # Required fields
    buyer_ref: str = Field(..., description="Buyer's reference identifier")

    # Optional fields (allows partial success)
    media_buy_id: str | None = Field(None, description="Publisher's unique identifier")
    packages: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[Error] | None = Field(None, description="Task-specific errors")
```

**What needs to change:**
We need to model the `oneOf` discriminator in Pydantic. Two approaches:

#### Approach A: Union Types (Recommended)
```python
from typing import Union
from pydantic import Field, model_validator

class CreateMediaBuySuccess(AdCPBaseModel):
    """Success branch: operation completed fully."""
    media_buy_id: str = Field(..., description="Publisher's unique identifier")
    buyer_ref: str = Field(..., description="Buyer's reference identifier")
    packages: list[Package] = Field(..., description="Created packages")
    creative_deadline: datetime | None = None

    @model_validator(mode='after')
    def forbid_errors(self):
        if hasattr(self, 'errors') and self.errors is not None:
            raise ValueError("Success response cannot contain errors")
        return self

class CreateMediaBuyError(AdCPBaseModel):
    """Error branch: operation failed."""
    buyer_ref: str = Field(..., description="Buyer's reference identifier")
    errors: list[Error] = Field(..., description="Why operation failed")

    @model_validator(mode='after')
    def forbid_success_fields(self):
        if hasattr(self, 'media_buy_id') and self.media_buy_id is not None:
            raise ValueError("Error response cannot contain media_buy_id")
        return self

# Use discriminated union
CreateMediaBuyResponse = Union[CreateMediaBuySuccess, CreateMediaBuyError]
```

#### Approach B: Pydantic Discriminated Unions
```python
from typing import Annotated, Literal
from pydantic import Field, Tag

class CreateMediaBuySuccess(AdCPBaseModel):
    status: Literal["success"] = "success"  # Discriminator field
    media_buy_id: str
    buyer_ref: str
    packages: list[Package]

class CreateMediaBuyError(AdCPBaseModel):
    status: Literal["error"] = "error"  # Discriminator field
    buyer_ref: str
    errors: list[Error]

CreateMediaBuyResponse = Annotated[
    Union[CreateMediaBuySuccess, CreateMediaBuyError],
    Field(discriminator='status')
]
```

**Recommendation: Approach A** - Mirrors the JSON schema more directly, no extra discriminator field.

### 2. Implementation Changes Required

**Affected operations:**
- `create_media_buy` → CreateMediaBuyResponse
- `update_media_buy` → UpdateMediaBuyResponse
- `build_creative` → BuildCreativeResponse
- `sync_creatives` → SyncCreativesResponse (special case)
- `provide_performance_feedback` → ProvidePerformanceFeedbackResponse
- `activate_signal` → ActivateSignalResponse
- `webhook_payload` → WebhookPayload (conditional)

**Migration strategy:**
```python
# src/core/main.py - _create_media_buy_impl()

def _create_media_buy_impl(...) -> Union[CreateMediaBuySuccess, CreateMediaBuyError]:
    try:
        # Existing implementation
        media_buy = orchestrator.create_media_buy(...)

        # Validate ALL constraints were applied
        if not all_constraints_fulfilled(media_buy, request):
            # Instead of partial success, return error
            return CreateMediaBuyError(
                buyer_ref=request.buyer_ref,
                errors=[Error(
                    code="CONSTRAINT_FULFILLMENT_FAILED",
                    message="Could not fulfill all targeting constraints",
                    details={"unsupported": ["dayparting", "device_targeting"]}
                )]
            )

        # True success: ALL constraints applied
        return CreateMediaBuySuccess(
            media_buy_id=media_buy.media_buy_id,
            buyer_ref=request.buyer_ref,
            packages=[...],
            creative_deadline=media_buy.creative_deadline
        )

    except Exception as e:
        # Errors always return error branch
        return CreateMediaBuyError(
            buyer_ref=request.buyer_ref,
            errors=[Error(code="INTERNAL_ERROR", message=str(e))]
        )
```

**Key insight:** This forces us to be **explicit** about what constitutes success vs failure.

### 3. Testing Impact

**Current tests need updates:**

```python
# tests/integration/test_create_media_buy.py

def test_create_media_buy_success(integration_db):
    """Test successful media buy creation."""
    response = _create_media_buy_impl(...)

    # OLD: Check fields exist
    assert response.media_buy_id is not None
    assert response.errors is None

    # NEW: Use type narrowing
    assert isinstance(response, CreateMediaBuySuccess)
    assert response.media_buy_id  # Always present in success case
    # No need to check errors - they can't exist in this branch
```

**Benefits:**
- Tests become more explicit about success vs failure cases
- Type checkers (mypy) can verify we're handling both branches
- No more "assert errors is None" - impossible in success branch

### 4. Special Case: `sync_creatives`

The PR notes this operation has **dual-level error handling:**
- **Operation-level**: Did the sync operation itself succeed?
- **Item-level**: Which individual creatives succeeded/failed?

```python
class SyncCreativesSuccess(AdCPBaseModel):
    """Operation succeeded, but individual items may have errors."""
    creatives: list[SyncCreativeResult]  # Each has its own status
    dry_run: bool | None = None

class SyncCreativesError(AdCPBaseModel):
    """Operation failed completely (e.g., auth failure)."""
    errors: list[Error]

# Where SyncCreativeResult contains per-item status:
class SyncCreativeResult(BaseModel):
    creative_id: str
    status: Literal["success", "error"]
    error_message: str | None = None
```

This preserves batch semantics while maintaining atomic operation boundaries.

---

## TypeScript Schema Generation

### Current Challenge
Without `oneOf` discriminators, TypeScript generators produce **permissive types:**

```typescript
// BEFORE (current schema)
interface CreateMediaBuyResponse {
  media_buy_id?: string;      // Optional
  buyer_ref: string;          // Required
  packages?: Package[];       // Optional
  errors?: Error[];           // Optional
}

// Problem: This allows nonsensical states
const response: CreateMediaBuyResponse = {
  buyer_ref: "123",
  media_buy_id: "mb_789",   // Success indicator
  errors: [...]             // But also has errors?!
};
```

### With OneOf (Proposed)
TypeScript generators naturally map `oneOf` to **discriminated unions:**

```typescript
// AFTER (with oneOf)
type CreateMediaBuyResponse =
  | CreateMediaBuySuccess
  | CreateMediaBuyError;

interface CreateMediaBuySuccess {
  media_buy_id: string;     // Required!
  buyer_ref: string;
  packages: Package[];      // Required!
  creative_deadline?: string;
  // errors is FORBIDDEN (type system enforces)
}

interface CreateMediaBuyError {
  buyer_ref: string;
  errors: Error[];          // Required!
  // media_buy_id is FORBIDDEN
}

// TypeScript compiler prevents invalid states
const invalid: CreateMediaBuyResponse = {
  buyer_ref: "123",
  media_buy_id: "mb_789",
  errors: [...]  // ❌ Type error: cannot have both
};

// Forces explicit handling
function handleResponse(response: CreateMediaBuyResponse) {
  if ('media_buy_id' in response) {
    // Type narrowed to CreateMediaBuySuccess
    console.log(response.media_buy_id);  // ✅ Always present
    console.log(response.errors);        // ❌ Compile error
  } else {
    // Type narrowed to CreateMediaBuyError
    console.log(response.errors);        // ✅ Always present
    console.log(response.media_buy_id);  // ❌ Compile error
  }
}
```

### Benefits for TypeScript

1. **Type Safety**: Impossible states become unrepresentable
2. **Exhaustiveness Checking**: Compiler ensures you handle all cases
3. **Better IntelliSense**: IDE knows exactly what fields are available
4. **Clear Intent**: Union types make success/error paths explicit
5. **Easier Generation**: `oneOf` maps directly to TypeScript unions

**Example with popular generators:**

```bash
# Using quicktype
quicktype schemas/v1/media-buy/create-media-buy-response.json -o types.ts

# Output (with oneOf):
export type CreateMediaBuyResponse = CreateMediaBuySuccess | CreateMediaBuyError;

export interface CreateMediaBuySuccess {
    media_buy_id: string;
    buyer_ref: string;
    packages: Package[];
    creative_deadline?: string;
}

export interface CreateMediaBuyError {
    buyer_ref: string;
    errors: Error[];
}
```

**This is CLEANER and SAFER than the current approach.**

---

## Migration Effort Estimate

### Phase 1: Schema Updates (1-2 days)
- [ ] Update Pydantic schemas to use Union types (6 response models)
- [ ] Add model validators to enforce `not` constraints
- [ ] Update type hints throughout codebase

### Phase 2: Implementation Updates (2-3 days)
- [ ] Update tool implementations to return explicit success/error branches
- [ ] Add constraint validation logic (ensure ALL requirements met before success)
- [ ] Update error handling to use error branch consistently

### Phase 3: Test Updates (1-2 days)
- [ ] Update unit tests to use type narrowing
- [ ] Add contract tests for oneOf validation
- [ ] Update integration tests to verify atomic semantics

### Phase 4: Documentation (1 day)
- [ ] Update CLAUDE.md with new patterns
- [ ] Document migration guide for other implementers
- [ ] Update API documentation

**Total Estimate: 5-8 days** for full migration.

---

## Potential Issues & Mitigations

### Issue 1: Breaking Change
**Problem:** Existing clients expect optional `media_buy_id` field.

**Mitigation:**
- Version the schemas (v1 → v2)
- Support both patterns during transition period
- Use environment-based validation (development strict, production lenient)

### Issue 2: Batch Operations
**Problem:** `sync_creatives` has dual-level errors.

**Mitigation:**
- Operation-level oneOf for sync failure vs success
- Item-level status in `SyncCreativeResult` for per-item errors
- Already documented in PR

### Issue 3: Webhook Payload Complexity
**Problem:** Webhooks need conditional validation based on `task_type`.

**Mitigation:**
- Use Pydantic's `model_validator` with mode='wrap'
- Validate against appropriate response schema based on task_type
- Test all task types thoroughly

### Issue 4: Testing Hook Fields
**Problem:** We add `dry_run`, `test_session_id` via `apply_testing_hooks`.

**Mitigation:**
- Testing hook fields are INTERNAL (not in AdCP schema)
- Apply after response construction, not before
- Use `model_dump_internal()` which excludes them from AdCP output
- No change needed to testing infrastructure

---

## Recommendations

### ✅ Strongly Support This Change

**Reasons:**
1. **Safety First**: Prevents partial success bugs that could cost money
2. **Better Type Safety**: TypeScript generation becomes cleaner
3. **Explicit Error Handling**: Forces us to be clear about success criteria
4. **Industry Standard**: `oneOf` is widely supported and well-understood
5. **Backward Compatible Path**: Can version schemas during migration

### Implementation Order

1. **Start with `create_media_buy`** - Most critical operation
2. **Then `update_media_buy`** - Second most critical
3. **Then batch operations** (`sync_creatives`) - More complex
4. **Finally signals** - Lower priority

### Testing Strategy

```python
# Add contract tests for oneOf validation
def test_create_media_buy_oneOf_validation():
    """Verify oneOf constraints are enforced."""

    # Valid success response
    success = CreateMediaBuySuccess(
        media_buy_id="mb_123",
        buyer_ref="ref_456",
        packages=[...]
    )
    assert isinstance(success, CreateMediaBuySuccess)

    # Valid error response
    error = CreateMediaBuyError(
        buyer_ref="ref_456",
        errors=[Error(code="FAILED", message="Reason")]
    )
    assert isinstance(error, CreateMediaBuyError)

    # Invalid: both success and error indicators
    with pytest.raises(ValidationError):
        invalid = {
            "media_buy_id": "mb_123",  # Success indicator
            "buyer_ref": "ref_456",
            "errors": [...]             # Error indicator - FORBIDDEN
        }
        CreateMediaBuySuccess(**invalid)
```

---

## TypeScript Generation Specifics

### Recommended Tool: json-schema-to-typescript

```bash
npm install -g json-schema-to-typescript

# Generate TypeScript from updated schemas
json2ts schemas/v1/media-buy/create-media-buy-response.json > types/CreateMediaBuyResponse.ts
```

**Output quality with oneOf:**
```typescript
/**
 * Response payload for create_media_buy task
 */
export type CreateMediaBuyResponse = CreateMediaBuySuccess | CreateMediaBuyError;

/**
 * Success response
 */
export interface CreateMediaBuySuccess {
  media_buy_id: string;
  buyer_ref: string;
  packages: Package[];
  creative_deadline?: string;
}

/**
 * Error response
 */
export interface CreateMediaBuyError {
  buyer_ref: string;
  errors: Error[];
}
```

**Usage in TypeScript clients:**
```typescript
import { CreateMediaBuyResponse } from './types';

async function createMediaBuy(request: CreateMediaBuyRequest): Promise<CreateMediaBuyResponse> {
  const response = await fetch('/api/media-buy', {
    method: 'POST',
    body: JSON.stringify(request)
  });

  const data = await response.json() as CreateMediaBuyResponse;

  // TypeScript forces you to handle both cases
  if ('media_buy_id' in data) {
    // Success case
    console.log(`Created media buy: ${data.media_buy_id}`);
    return data;  // Type: CreateMediaBuySuccess
  } else {
    // Error case
    throw new Error(`Media buy creation failed: ${data.errors[0].message}`);
  }
}
```

### Alternative: OpenAPI Generator

If we eventually expose REST APIs:

```yaml
# openapi.yaml
components:
  schemas:
    CreateMediaBuyResponse:
      oneOf:
        - $ref: '#/components/schemas/CreateMediaBuySuccess'
        - $ref: '#/components/schemas/CreateMediaBuyError'
      discriminator:
        propertyName: status  # Optional explicit discriminator
```

```bash
openapi-generator-cli generate -i openapi.yaml -g typescript-axios -o ./client
```

**Result:** Same discriminated union types as json-schema-to-typescript.

---

## Conclusion

**This PR is a NET POSITIVE for the AdCP ecosystem.**

### Pros (Strong)
- ✅ Eliminates dangerous partial success states
- ✅ Improves TypeScript generation significantly
- ✅ Makes error handling explicit and type-safe
- ✅ Industry-standard pattern (oneOf widely supported)
- ✅ Forces implementers to think about success criteria

### Cons (Manageable)
- ⚠️ Breaking change requiring migration
- ⚠️ More complex schema structure (but clearer semantics)
- ⚠️ Requires thoughtful batch operation handling

### Bottom Line

**Support and implement this change.** The safety improvements and TypeScript benefits far outweigh the migration cost.

**Estimated Timeline:**
- Schema updates: 1-2 days
- Implementation: 2-3 days
- Testing: 1-2 days
- Documentation: 1 day
- **Total: ~1 week of focused work**

**Risk Level:** Low (with proper testing and phased rollout)

---

## Next Steps

If you want to proceed with this:

1. **Comment on PR #186** supporting the change
2. **Request timeline** for when this will be merged
3. **Plan migration** - I can help implement the Pydantic schema updates
4. **Set up TypeScript generation** - We should add this to our repo
5. **Update documentation** - Add oneOf patterns to CLAUDE.md

Let me know if you want me to start implementing the Pydantic schema changes!
