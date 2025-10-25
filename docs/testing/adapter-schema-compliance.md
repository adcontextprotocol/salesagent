# Adapter Schema Compliance Testing

## Overview

This document explains how we ensure `schema_adapters.py` stays in sync with the official AdCP JSON schemas, preventing field mismatches that would cause response construction errors.

## The Problem

We have three schema layers:

1. **Official AdCP JSON Schemas** (`schemas/v1/*.json`) - Source of truth from https://adcontextprotocol.org
2. **Base Pydantic Schemas** (`src/core/schemas.py`) - Generated from JSON schemas, domain data only
3. **Adapter Schemas** (`src/core/schema_adapters.py`) - Wrap base schemas, add `__str__()` for protocol abstraction

The `main.py` implementation uses **adapter schemas** to construct responses. If adapter schemas drift from the official spec, we'll construct invalid responses that fail client validation.

**Real Example:**
- Official spec has `advertising_policies` field in `ListAuthorizedPropertiesResponse`
- Adapter schema was missing this field
- Pre-commit hook (`validate-adapter-usage`) failed because code tried to use the field
- Without sync verification, we'd either:
  - Remove the field from code (lose functionality)
  - Add it to adapter without verifying spec (might be wrong)

## The Solution

### 1. Automated Compliance Testing

**File:** `tests/unit/test_adapter_schema_compliance.py`

This test file validates that adapter schemas match official JSON schemas by:

1. **Loading official schemas** from cached JSON files
2. **Extracting Pydantic fields** from adapter models
3. **Comparing field names and requirements** between spec and implementation
4. **Failing tests** if fields are missing or have incorrect `required` status

**Example test:**

```python
def test_list_authorized_properties_response_matches_spec(self):
    """Test ListAuthorizedPropertiesResponse has all AdCP spec fields."""
    # Load official schema
    official_schema = self.load_official_schema("ListAuthorizedPropertiesResponse")
    official_fields = self.extract_json_schema_fields(official_schema)

    # Extract Pydantic model fields
    adapter_fields = self.extract_pydantic_fields(ListAuthorizedPropertiesResponse)

    # Check that all official fields are in adapter
    missing_fields = []
    for field_name, field_info in official_fields.items():
        if field_name not in adapter_fields:
            missing_fields.append(f"{field_name} (required={field_info['required']})")

    if missing_fields:
        pytest.fail(f"Missing fields: {', '.join(missing_fields)}")
```

### 2. Pre-Commit Hook Integration

**File:** `.pre-commit-config.yaml`

```yaml
- id: adapter-schema-compliance
  name: Validate adapter schemas match AdCP spec
  entry: uv run pytest tests/unit/test_adapter_schema_compliance.py -v --tb=short
  language: system
  files: '^(src/core/schema_adapters\.py|schemas/v1/.*\.json)$'
  pass_filenames: false
  always_run: true
```

**When it runs:**
- On every commit (if `schema_adapters.py` or JSON schemas changed)
- With `always_run: true` to catch drift proactively

**What it catches:**
- Missing fields in adapter schemas
- Incorrect `required` vs optional status
- Typos in field names

### 3. Pydantic Field Introspection

We use Pydantic's `model_fields` to extract metadata:

```python
@staticmethod
def extract_pydantic_fields(model: type[BaseModel]) -> dict[str, dict[str, Any]]:
    """Extract field definitions from Pydantic model."""
    fields = {}
    for field_name, field_info in model.model_fields.items():
        fields[field_name] = {
            "required": field_info.is_required(),
            "type": str(field_info.annotation),
        }
    return fields
```

This provides:
- Field names
- Required vs optional status
- Type annotations (for future validation)

### 4. JSON Schema Parsing

We parse official JSON schemas to extract field metadata:

```python
@staticmethod
def extract_json_schema_fields(json_schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract field definitions from JSON schema."""
    properties = json_schema.get("properties", {})
    required_fields = set(json_schema.get("required", []))

    fields = {}
    for field_name, field_def in properties.items():
        fields[field_name] = {
            "required": field_name in required_fields,
            "type": field_def.get("type", "unknown"),
            "description": field_def.get("description", ""),
        }
    return fields
```

## Coverage Status

**Currently tested:**
- ✅ `ListAuthorizedPropertiesResponse` - Caught missing `advertising_policies`
- ✅ `GetSignalsResponse` - Validates `message`, `context_id`, `signals`
- ✅ `ActivateSignalResponse` - Validates `task_id`, `status`, etc.
- ✅ `UpdateMediaBuyResponse` - Caught missing `implementation_date`
- ✅ `ListCreativesResponse` - Validates query_summary, pagination, creatives

**TODO (tracked in test file):**
- ⏳ `CreateMediaBuyResponse`
- ⏳ `GetProductsResponse`
- ⏳ `GetMediaBuyDeliveryResponse`
- ⏳ `ListCreativeFormatsResponse`
- ⏳ `SyncCreativesResponse`

## Complementary Tools

This compliance testing works alongside other validation tools:

### 1. `validate-adapter-usage` (Pre-commit Hook)

**File:** `scripts/validate_adapter_usage.py`

- Validates that `main.py` constructs responses using correct field names
- Uses AST parsing to find constructor calls
- Compares against `schema_adapters.py` field definitions
- **Complements compliance tests** by catching usage errors

**Example:**
```python
# ❌ Wrong - 'status' not in UpdateMediaBuyResponse adapter schema
return UpdateMediaBuyResponse(
    status="completed",  # Hook catches this!
    buyer_ref="ref_123",
)

# ✅ Correct
return UpdateMediaBuyResponse(
    buyer_ref="ref_123",
    media_buy_id="mb_456",
)
```

### 2. `test_adcp_contract.py` (Unit Tests)

**File:** `tests/unit/test_adcp_contract.py`

- Tests that base `schemas.py` models match AdCP spec
- Validates `model_dump()` output structure
- Tests with real data to ensure serialization works

**Example:**
```python
def test_list_authorized_properties_response_contract(self):
    """Test that ListAuthorizedPropertiesResponse complies with AdCP spec."""
    response = ListAuthorizedPropertiesResponse(
        properties=[...],
        tags={...},
    )

    adcp_response = response.model_dump()

    # Verify required fields present
    required_fields = ["properties"]
    for field in required_fields:
        assert field in adcp_response
        assert adcp_response[field] is not None

    # Verify optional fields present (can be null)
    optional_fields = ["tags", "advertising_policies", ...]
    for field in optional_fields:
        assert field in adcp_response
```

### 3. `adcp_schema_validator.py` (E2E Tests)

**File:** `tests/e2e/adcp_schema_validator.py`

- Downloads and caches official schemas from https://adcontextprotocol.org
- Validates actual API responses against JSON schemas using `jsonschema` library
- Catches runtime schema violations

## How mypy Helps

While mypy doesn't directly validate against JSON schemas, it provides complementary type safety:

### 1. Field Existence Checking

```python
from src.core.schema_adapters import ListAuthorizedPropertiesResponse

response = ListAuthorizedPropertiesResponse(
    properties=[],
    tags={},
    advertising_policies="Our policies...",  # mypy knows this field exists
    unknown_field="value",  # ❌ mypy error: unexpected keyword argument
)
```

### 2. Type Annotations

```python
class ListAuthorizedPropertiesResponse(AdCPBaseModel):
    advertising_policies: str | None = Field(...)  # mypy enforces str or None

# Usage
response.advertising_policies = 123  # ❌ mypy error: int not compatible with str | None
```

### 3. SQLAlchemy 2.0 Integration

```python
from sqlalchemy.orm import Mapped, mapped_column

class MyModel(Base):
    # mypy validates Mapped[] types match column types
    config: Mapped[dict] = mapped_column(JSONType, nullable=False)
    tags: Mapped[Optional[list]] = mapped_column(JSONType, nullable=True)
```

## Best Practices

### When Adding New Fields

1. **Verify field exists in official AdCP spec first:**
   ```bash
   # Check cached schema
   cat schemas/v1/_schemas_v1_media-buy_list-authorized-properties-response_json.json
   ```

2. **Add field to adapter schema:**
   ```python
   class ListAuthorizedPropertiesResponse(AdCPBaseModel):
       new_field: str | None = Field(None, description="From AdCP spec")
   ```

3. **Run compliance test:**
   ```bash
   pytest tests/unit/test_adapter_schema_compliance.py -v
   ```

4. **Update implementation in `main.py`:**
   ```python
   return ListAuthorizedPropertiesResponse(
       properties=properties,
       tags=tag_metadata,
       new_field=computed_value,  # Use the new field
   )
   ```

### When Schemas Update

1. **E2E tests auto-download** new schemas from https://adcontextprotocol.org
2. **Compliance tests compare** against cached schemas
3. **Pre-commit hooks catch drift** automatically
4. **Fix adapter schemas** to match updated spec

### Debugging Validation Failures

**Pre-commit hook fails:**
```
FAILED tests/unit/test_adapter_schema_compliance.py::...::test_update_media_buy_response_matches_spec
Missing: implementation_date (required=False)
```

**How to fix:**
1. Check official schema: `schemas/v1/_schemas_v1_media-buy_update-media-buy-response_json.json`
2. Verify field is in spec (lines 60-65 show `implementation_date`)
3. Add field to `schema_adapters.py`:
   ```python
   implementation_date: str | None = Field(None, description="ISO 8601 date...")
   ```
4. Re-run test: `pytest tests/unit/test_adapter_schema_compliance.py`

## Future Enhancements

### 1. Type Validation

Currently we only check field names and requirements. Could add:

```python
def validate_field_types(official_type: str, pydantic_type: str) -> bool:
    """Validate that Pydantic type matches JSON schema type."""
    type_mappings = {
        "string": ["str", "str | None"],
        "integer": ["int", "int | None"],
        "array": ["list[", "list | None"],
        "object": ["dict", "dict | None"],
    }
    return any(pt in pydantic_type for pt in type_mappings.get(official_type, []))
```

### 2. Automated Field Addition

Generate adapter schemas from JSON schemas:

```bash
# Generate adapter schema from official spec
python scripts/generate_adapter_schema.py \
    --spec schemas/v1/_schemas_v1_media-buy_list-authorized-properties-response_json.json \
    --output src/core/schema_adapters.py \
    --class-name ListAuthorizedPropertiesResponse
```

### 3. CI/CD Integration

Add to GitHub Actions:

```yaml
- name: Validate Adapter Schema Compliance
  run: |
    pytest tests/unit/test_adapter_schema_compliance.py -v
    if [ $? -ne 0 ]; then
      echo "❌ Adapter schemas out of sync with AdCP spec!"
      echo "See docs/testing/adapter-schema-compliance.md"
      exit 1
    fi
```

## Related Documentation

- [AdCP Compliance Testing](./adcp-compliance.md) - Base schema validation
- [Testing Guidelines](../../CLAUDE.md#testing-guidelines) - Overall testing strategy
- [AdCP Schema Source of Truth](../../CLAUDE.md#adcp-schema-source-of-truth) - Schema hierarchy
- [Official AdCP Spec](https://adcontextprotocol.org/schemas/v1/) - Source of truth

## Summary

**The adapter schema compliance system ensures:**

1. ✅ **Adapter schemas match official spec** - Pydantic field introspection vs JSON schema parsing
2. ✅ **Caught in pre-commit** - Runs automatically, fails fast
3. ✅ **Clear error messages** - Lists missing fields with required status
4. ✅ **Complementary to existing tools** - Works with validate-adapter-usage, contract tests, E2E validation
5. ✅ **Low maintenance** - Tests are declarative, just add new test methods for new adapters

**Key insight:** By validating at multiple layers (JSON schema → Pydantic schema → adapter schema → usage in main.py), we catch schema drift at the earliest possible point.
