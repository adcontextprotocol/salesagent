# Systematic Fix Plan: Nested Model Serialization Vulnerability

## Executive Summary

**Confirmed Pydantic Behavior**: When a parent model calls `model_dump()`, Pydantic does NOT automatically call custom `model_dump()` methods on nested child models. This causes internal fields to leak in responses.

**Scope**: 7 HIGH RISK response models are confirmed vulnerable.

**Impact**: Internal fields (like `principal_id`, `created_at`, `status`, `tenant_id`) leak in API responses, violating AdCP spec compliance and potentially exposing sensitive data.

---

## Proof of Vulnerability

### Test Results

```python
# Nested model with custom model_dump() to exclude internal_field
class NestedModel(BaseModel):
    name: str
    internal_field: str | None = None

    def model_dump(self, **kwargs):
        exclude = kwargs.get('exclude', set())
        if isinstance(exclude, set):
            exclude.add('internal_field')
            kwargs['exclude'] = exclude
        return super().model_dump(**kwargs)

# Parent model with list of nested models
class ParentModel(BaseModel):
    items: list[NestedModel]

# Direct call: internal_field excluded ✅
nested.model_dump()  # {'name': 'test'}

# Parent call: internal_field LEAKED ❌
ParentModel(items=[nested]).model_dump()  # {'items': [{'name': 'test', 'internal_field': 'secret'}]}
```

**Result**: Pydantic's default serialization bypasses custom `model_dump()` on nested models.

---

## Confirmed Vulnerable Models

### 1. ListCreativesResponse (CRITICAL)
**File**: `src/core/schemas.py:1832`
**Nested Model**: `list[Creative]`
**Internal Fields in Creative**: `principal_id`, `created_at`, `updated_at`, `status`
**Impact**: Advertiser IDs and internal workflow states leak to clients
**Used By**: MCP `list_creatives`, A2A `/creatives` endpoint

### 2. CreateCreativeResponse (CRITICAL)
**File**: `src/core/schemas.py` (find line)
**Nested Model**: `Creative`
**Internal Fields**: Same as above
**Impact**: Same as above
**Used By**: Creative sync operations

### 3. GetCreativesResponse (CRITICAL)
**File**: `src/core/schemas.py` (find line)
**Nested Model**: `list[Creative]`, `list[CreativeAssignment]`
**Internal Fields**: Same as above
**Impact**: Same as above
**Used By**: Admin UI, internal tools

### 4. GetSignalsResponse (HIGH)
**File**: `src/core/schemas.py` (find line)
**Nested Model**: `list[Signal]`
**Internal Fields in Signal**: `tenant_id`, `created_at`, `updated_at`, `metadata`
**Impact**: Tenant IDs and internal metadata leak
**Used By**: MCP `get_signals`, A2A signals endpoints

### 5. GetMediaBuyDeliveryResponse (MEDIUM-HIGH)
**File**: `src/core/schemas.py` (find line)
**Nested Models**: `list[MediaBuyDeliveryData]` (3 levels deep!)
**Internal Fields**: Need verification
**Impact**: Potential internal metrics or IDs leak
**Used By**: MCP `get_media_buy_delivery`, reporting

### 6. GetPendingTasksResponse (MEDIUM - Internal Only)
**File**: `src/core/schemas.py` (find line)
**Nested Model**: `list[HumanTask]`
**Internal Fields**: Many workflow management fields
**Impact**: Internal task management details leak
**Used By**: Admin UI only (lower risk)

### 7. GetAllMediaBuyDeliveryResponse (LOW - Deprecated)
**File**: `src/core/schemas.py` (find line)
**Nested Model**: Same as GetMediaBuyDeliveryResponse
**Impact**: Same as above (but deprecated)
**Used By**: Legacy endpoint (being phased out)

---

## Fix Pattern (Proven Solution)

### Template Code

```python
class MyResponse(AdCPBaseModel):
    """Response with nested models."""

    nested_list: list[NestedModel] = Field(...)
    nested_object: NestedModel | None = Field(None)

    def model_dump(self, **kwargs):
        """Override to ensure nested models use their custom model_dump()."""
        # Get base dump (uses Pydantic's default nested serialization)
        result = super().model_dump(**kwargs)

        # Explicitly re-serialize list of nested models
        if "nested_list" in result and self.nested_list:
            result["nested_list"] = [item.model_dump(**kwargs) for item in self.nested_list]

        # Explicitly re-serialize single nested model
        if "nested_object" in result and self.nested_object:
            result["nested_object"] = self.nested_object.model_dump(**kwargs)

        return result
```

### Example Fix for ListCreativesResponse

```python
class ListCreativesResponse(AdCPBaseModel):
    """Response from listing creative assets."""

    query_summary: QuerySummary
    pagination: Pagination
    creatives: list[Creative]
    format_summary: dict[str, int] | None = None
    status_summary: dict[str, int] | None = None

    def model_dump(self, **kwargs):
        """Override to ensure nested Creative objects use their custom model_dump()."""
        result = super().model_dump(**kwargs)

        # Explicitly serialize creatives using their custom model_dump()
        # which excludes internal fields (principal_id, created_at, updated_at, status)
        if "creatives" in result and self.creatives:
            result["creatives"] = [creative.model_dump(**kwargs) for creative in self.creatives]

        return result
```

---

## Implementation Plan

### Phase 1: Critical Fixes (Week 1)

**Priority Order**:
1. **ListCreativesResponse** - Most used, clear internal fields
2. **CreateCreativeResponse** - Creative sync operations
3. **GetCreativesResponse** - Admin UI
4. **GetSignalsResponse** - Signals API

**For each model**:
1. Add `model_dump()` override following template
2. Add unit test verifying internal fields excluded
3. Add generated schema validation test (like `test_sync_creatives_generated_schema_validation.py`)
4. Run all existing tests to ensure no breakage
5. Commit with clear message referencing this plan

### Phase 2: Verification (Week 1)

**Verify fixes**:
1. Run full test suite: `./run_all_tests.sh ci`
2. Test against actual clients (JS and Python)
3. Verify AdCP spec compliance for all fixed endpoints
4. Check E2E tests pass

### Phase 3: Medium Priority (Week 2)

1. **GetMediaBuyDeliveryResponse** - Verify nested structure
2. **GetPendingTasksResponse** - Internal admin tool
3. **GetAllMediaBuyDeliveryResponse** - Deprecated (consider removing)

### Phase 4: Testing Infrastructure (Week 2)

**Add systematic tests**:
1. Create pre-commit hook to detect missing `model_dump()` on responses with nested models
2. Add CI check that validates ALL response models against generated schemas
3. Document pattern in CLAUDE.md testing guidelines
4. Create template for new response models

---

## Testing Strategy

### For Each Fixed Model

```python
def test_{model_name}_excludes_internal_fields_in_nested_models():
    """Test that nested models' internal fields are excluded."""
    # 1. Create nested model with internal fields
    nested = NestedModel(
        field="value",
        internal_field="secret"  # Should be excluded
    )

    # 2. Create response with nested model
    response = MyResponse(nested_list=[nested])

    # 3. Dump to dict (what clients receive)
    result = response.model_dump()

    # 4. Verify internal fields excluded
    assert "internal_field" not in result["nested_list"][0]

    # 5. Verify against generated schema
    from src.core.schemas_generated.xxx import GeneratedResponse
    validated = GeneratedResponse(**result)  # Should not raise ValidationError
    assert validated is not None
```

### Regression Prevention

Add to `tests/unit/test_response_serialization_patterns.py`:

```python
def test_all_response_models_with_nested_objects_have_custom_model_dump():
    """Ensure all response models with nested Pydantic models have custom model_dump()."""
    import inspect
    from src.core.schemas import AdCPBaseModel

    # Get all response models
    response_models = [
        cls for name, cls in inspect.getmembers(schemas, inspect.isclass)
        if issubclass(cls, AdCPBaseModel) and name.endswith('Response')
    ]

    for model in response_models:
        # Check if model has nested Pydantic models
        has_nested = False
        for field_name, field_info in model.model_fields.items():
            # Check if field is list[Model] or Model
            if is_nested_pydantic_model(field_info.annotation):
                has_nested = True
                break

        if has_nested:
            # Verify it has custom model_dump()
            has_custom_dump = 'model_dump' in model.__dict__
            assert has_custom_dump, f"{model.__name__} has nested models but no custom model_dump()"
```

---

## Checklist for Each Fix

- [ ] Identify all nested model fields
- [ ] Check if nested models have custom `model_dump()`
- [ ] Add `model_dump()` override to parent response
- [ ] Write unit test verifying internal fields excluded
- [ ] Write generated schema validation test
- [ ] Run existing tests (ensure no breakage)
- [ ] Manual test with actual client
- [ ] Commit with clear message
- [ ] Update TESTING_IMPROVEMENT_SUMMARY.md

---

## Long-Term Prevention

### 1. Pre-Commit Hook
Add check for response models with nested models but no custom `model_dump()`:

```bash
# .pre-commit-config.yaml
- id: check-response-serialization
  name: Check response models have proper serialization
  entry: scripts/hooks/check_response_serialization.py
  language: python
  files: ^src/core/schemas\.py$
```

### 2. Documentation
Add to CLAUDE.md:

```markdown
### Response Models with Nested Objects

When creating response models with nested Pydantic models:

1. **Check if nested model has custom model_dump()** (e.g., excludes internal fields)
2. **Add custom model_dump() to parent** to explicitly serialize nested models
3. **Test against generated schema** to ensure compliance
4. **Add unit test** verifying internal fields excluded

Pattern:
\```python
def model_dump(self, **kwargs):
    result = super().model_dump(**kwargs)
    if "nested_field" in result and self.nested_field:
        result["nested_field"] = [item.model_dump(**kwargs) for item in self.nested_field]
    return result
\```
```

### 3. Template for New Response Models

Create `templates/response_model_template.py`:

```python
class NewResponse(AdCPBaseModel):
    """Response description."""

    # Fields
    items: list[ItemModel] = Field(...)

    def model_dump(self, **kwargs):
        """Override to ensure nested models use their custom model_dump()."""
        result = super().model_dump(**kwargs)

        # TODO: Add nested serialization for each field with nested models
        if "items" in result and self.items:
            result["items"] = [item.model_dump(**kwargs) for item in self.items]

        return result

    def __str__(self) -> str:
        """Return human-readable message for protocol layer."""
        # TODO: Implement
        return f"Response with {len(self.items)} items"
```

---

## Timeline

**Week 1**:
- Day 1-2: Fix ListCreativesResponse, CreateCreativeResponse, GetCreativesResponse
- Day 3: Fix GetSignalsResponse
- Day 4: Write and run all tests
- Day 5: Review and merge

**Week 2**:
- Day 1-2: Fix GetMediaBuyDeliveryResponse and GetPendingTasksResponse
- Day 3: Add pre-commit hook and CI checks
- Day 4: Documentation updates
- Day 5: Final review and deployment

---

## Success Metrics

1. ✅ All 7 HIGH RISK models fixed
2. ✅ All internal fields excluded from responses
3. ✅ All responses validate against generated schemas
4. ✅ No client validation errors
5. ✅ Pre-commit hook prevents future bugs
6. ✅ Documentation updated with pattern

---

## References

- **Original Bug**: sync_creatives internal fields leak
- **Fix Commit**: f5bd7b8a
- **Test Commit**: e8c734ba
- **Analysis Doc**: TESTING_IMPROVEMENT_SUMMARY.md
- **Pydantic Docs**: https://docs.pydantic.dev/latest/concepts/serialization/#custom-serializers
