# CRITICAL: Schema Validation Failure Analysis

## Problem Summary

Our AdCP spec compliance is **completely broken**. We have:
1. ❌ Hardcoded tests that don't check against actual AdCP spec
2. ❌ Response schemas that don't match AdCP spec at all
3. ❌ No automated validation between our Pydantic models and AdCP JSON schemas
4. ❌ Multiple pre-commit hooks that don't catch this

## Specific Failure: sync_creatives Response

### What We Had
```python
class SyncCreativesResponse(BaseModel):
    synced_creatives: list[Creative]  # WRONG FIELD NAME
    failed_creatives: list[dict]
    assignments: list[CreativeAssignment]
    message: str | None
```

### What We Changed To (Still Wrong!)
```python
class SyncCreativesResponse(BaseModel):
    creatives: list[Creative]  # STILL WRONG!
    failed_creatives: list[dict]
    assignments: list[CreativeAssignment]
    message: str | None
```

### What The Actual AdCP Spec Says
**File**: `tests/e2e/schemas/v1/_schemas_v1_media-buy_sync-creatives-response_json.json`

**Required Fields**:
- `adcp_version`: string
- `message`: string
- `status`: enum (completed/working/submitted)

**Main Response Structure**:
- `results`: array of per-creative results (NOT `creatives`!)
  - Each result has: `creative_id`, `action` (created/updated/unchanged/failed), `status`, `platform_id`, `changes`, `errors`, etc.
- `summary`: object with counts
  - `total_processed`, `created`, `updated`, `unchanged`, `failed`, `deleted`
- `assignments_summary`: object with assignment counts
- `assignment_results`: array of assignment details

**We're completely missing**:
- adcp_version field
- status field (task status)
- context_id, task_id (for async)
- dry_run flag
- Proper summary structure
- Per-creative action tracking (created/updated/unchanged)
- Suggested adaptations
- Review feedback

## Root Cause Analysis

### 1. Hardcoded Tests Don't Validate Against Spec

**File**: `tests/unit/test_adcp_contract.py`

```python
# WRONG - Hardcoded field expectations
adcp_required_fields = ["synced_creatives"]  # Should read from actual spec!
```

**Why This Failed**:
- Tests check for hardcoded field names
- Tests don't load actual AdCP JSON schemas
- Tests don't validate structure matches spec
- When we change field names, we update tests to match (wrong direction!)

### 2. Schema Sync Script Only Checks JSON Files

**File**: `scripts/check_schema_sync.py`

**What it does**:
- ✅ Checks if `tests/e2e/schemas/v1/*.json` matches adcontextprotocol.org
- ❌ Does NOT check if our Pydantic models match those JSON schemas

**Missing**:
- No validation that `SyncCreativesResponse` matches `sync-creatives-response.json`
- No field-by-field comparison
- No type checking
- No required field validation

### 3. Multiple Hooks, None Catch This

**Pre-commit hooks that SHOULD have caught this**:
1. `adcp-contract-tests` - Runs hardcoded tests (useless)
2. `adcp-schema-sync` - Only checks JSON file freshness
3. `pydantic-adcp-alignment` - Apparently doesn't work?

**None of these**:
- Compare Pydantic field names to JSON schema properties
- Validate required fields match
- Check response structure
- Validate against actual spec

## Impact

**Severity**: 🔴 CRITICAL

**Affected**:
- All buyers using sync_creatives get wrong response format
- Response doesn't have task tracking (status, task_id, context_id)
- No proper error reporting per creative
- No summary statistics
- Clients have to implement workarounds

**Other Likely Broken Endpoints**:
- Probably ALL our responses don't match spec
- Need to audit: create_media_buy, update_media_buy, get_delivery, etc.

## Solution

### Immediate Fix Needed

1. **Create proper SyncCreativesResponse matching spec**
2. **Build automated validation tool**:
   ```python
   # scripts/validate_pydantic_against_schemas.py
   - Load JSON schema from tests/e2e/schemas/v1/*.json
   - Find corresponding Pydantic model
   - Compare:
     - Required fields match
     - Field names match
     - Field types compatible
     - Nested structures match
   - Exit 1 if mismatch
   ```

3. **Add to pre-commit**:
   ```yaml
   - id: validate-pydantic-schemas
     name: Validate Pydantic models match AdCP JSON schemas
     entry: uv run python scripts/validate_pydantic_against_schemas.py --strict
     files: '^src/core/schemas\.py$'
     always_run: true
   ```

4. **Fix test_adcp_contract.py**:
   - Load actual JSON schemas
   - Dynamically validate against spec
   - No hardcoded field lists

### Long-term Solution

1. **Generate Pydantic models from JSON schemas**
   - Use datamodel-code-generator
   - Generate from official AdCP schemas
   - Our schemas.py becomes generated code

2. **Pre-commit hook validates we haven't modified generated code**

3. **Schema updates automatically trigger regeneration**

## Action Items

- [ ] Audit ALL response models against AdCP spec
- [ ] Build validation script
- [ ] Fix SyncCreativesResponse properly
- [ ] Update all affected endpoints
- [ ] Add proper pre-commit validation
- [ ] Consider schema code generation
- [ ] Document schema update process

## Files to Review

- `src/core/schemas.py` - ALL Response models
- `tests/unit/test_adcp_contract.py` - Rewrite to use actual specs
- `scripts/check_schema_sync.py` - Add Pydantic validation
- `.pre-commit-config.yaml` - Add proper validation hook
- All response models need audit against JSON schemas in `tests/e2e/schemas/v1/`

## Lessons Learned

1. **Never hardcode test expectations** - Load from source of truth
2. **Validate at schema definition time** - Not at runtime
3. **Automate everything** - Humans miss things
4. **Test the tests** - Our validation wasn't validating
5. **Use code generation** - Don't manually sync schemas

## Priority

**This is P0** - We're violating the AdCP spec contract. Every buyer integration could be broken.
