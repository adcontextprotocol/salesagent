# Schema Fix Plan - CRITICAL P0

## Status
✅ Validation script built and working
🔴 6 Response models need fixing

## Validation Results

**Script**: `scripts/validate_pydantic_against_adcp_schemas.py`
**Run**: `docker-compose exec adcp-server python scripts/validate_pydantic_against_adcp_schemas.py`

**13 ERRORS found** across 6 response models that violate AdCP spec.

## Models That Need Fixing

### 1. SyncCreativesResponse (CRITICAL)
**Current**:
```python
class SyncCreativesResponse(BaseModel):
    creatives: list[Creative]  # WRONG - should be 'results'
    failed_creatives: list[dict]  # Wrong structure
    assignments: list[CreativeAssignment]
    message: str | None
```

**Required by Spec**:
- `adcp_version`: string (REQUIRED)
- `message`: string (REQUIRED)
- `status`: enum (completed/working/submitted) (REQUIRED)
- `summary`: object with counts (created, updated, unchanged, failed, deleted)
- `results`: array of per-creative results (NOT creatives!)
- `assignments_summary`: object
- `assignment_results`: array
- `context_id`, `task_id`, `dry_run`: optional

**Action**: Complete rewrite needed

### 2. CreateMediaBuyResponse
**Missing**: `adcp_version` (REQUIRED)
**Wrong**: `buyer_ref` and `status` should be REQUIRED

### 3. UpdateMediaBuyResponse
**Missing**: `adcp_version` (REQUIRED), `buyer_ref` (REQUIRED)
**Wrong**: `media_buy_id` should be REQUIRED

### 4. ListCreativesResponse
**Missing**: `adcp_version` (REQUIRED), `pagination` (REQUIRED), `query_summary` (REQUIRED)
**Has wrong fields**: `total_count`, `page`, `limit`, `has_more` (should be in `pagination` object)

### 5. GetProductsResponse
**Wrong**: `adcp_version` should be REQUIRED (currently optional)

### 6. GetDeliveryResponse
**No schema file found** - need to check if this endpoint exists in spec

## Implementation Steps

### Step 1: Add Common Fields to Base Response (DONE in some models)
All responses need:
```python
adcp_version: str = Field("2.3.0", pattern="^\\d+\\.\\d+\\.\\d+$")
```

### Step 2: Fix SyncCreativesResponse
Create nested models:
```python
class SyncSummary(BaseModel):
    total_processed: int
    created: int
    updated: int
    unchanged: int
    failed: int
    deleted: int = 0

class SyncCreativeResult(BaseModel):
    creative_id: str
    action: Literal["created", "updated", "unchanged", "failed", "deleted"]
    status: str | None = None
    platform_id: str | None = None
    changes: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

class SyncCreativesResponse(BaseModel):
    adcp_version: str = Field("2.3.0")
    message: str
    status: Literal["completed", "working", "submitted"] = "completed"
    summary: SyncSummary | None = None
    results: list[SyncCreativeResult] | None = None
    context_id: str | None = None
    task_id: str | None = None
    dry_run: bool = False
    assignments_summary: dict | None = None
    assignment_results: list[dict] | None = None
```

### Step 3: Update Implementation (src/core/main.py)
Change `_sync_creatives_impl()` to:
1. Track actions (created/updated/unchanged) per creative
2. Build `summary` object with counts
3. Build `results` array with per-creative details
4. Return new response structure

### Step 4: Update Tests
- Fix all test assertions to use `results` instead of `creatives`
- Update contract tests to load JSON schemas dynamically

### Step 5: Add to Pre-Commit
```yaml
- id: validate-pydantic-adcp
  name: Validate Pydantic models match AdCP schemas
  entry: uv run python scripts/validate_pydantic_against_adcp_schemas.py --strict
  language: system
  files: '^src/core/schemas\.py$'
  always_run: true
```

## Testing Strategy

1. Run validation script before and after each fix
2. Run unit tests: `pytest tests/unit/test_adcp_contract.py`
3. Run integration tests: `pytest tests/integration/test_creative_lifecycle_mcp.py`
4. Run e2e tests: `pytest tests/e2e/test_creative_lifecycle_end_to_end.py`
5. Manual test with MCP client

## Rollout Plan

### Phase 1: Fix Schemas (1-2 hours)
- Fix all 6 response models
- Update nested models
- Ensure validation passes

### Phase 2: Update Implementations (2-3 hours)
- Update `_sync_creatives_impl()`
- Update `_create_media_buy_impl()`
- Update other affected implementations
- Track proper actions/summaries

### Phase 3: Update Tests (1 hour)
- Fix all test assertions
- Update test_adcp_contract.py to be dynamic
- Ensure all tests pass

### Phase 4: Add Validation to CI (30 min)
- Add validation script to pre-commit
- Update CI to run validation
- Document process

## Files to Modify

1. **src/core/schemas.py** - Fix 6 response models
2. **src/core/main.py** - Update implementations
3. **tests/unit/test_adcp_contract.py** - Dynamic validation
4. **tests/integration/*.py** - Update assertions
5. **tests/e2e/*.py** - Update assertions
6. **.pre-commit-config.yaml** - Add validation hook

## Success Criteria

✅ Validation script reports 0 errors
✅ All unit tests pass
✅ All integration tests pass
✅ All e2e tests pass
✅ Pre-commit hook prevents future drift
✅ MCP client can call sync_creatives successfully

## Timeline

**Estimated**: 4-6 hours total
**Priority**: P0 - Blocks all buyer integrations
**Owner**: Needs immediate attention

## Next Steps

1. Start with SyncCreativesResponse (most critical, most used)
2. Update implementation
3. Fix tests
4. Move to next model
5. Repeat until all clean
