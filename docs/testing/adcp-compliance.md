# AdCP Protocol Compliance Testing

## Overview

All data models that represent AdCP protocol objects MUST be fully spec-compliant and tested.

## Compliance Requirements

### Response Models
- All models returned to clients must include ONLY AdCP spec-defined fields
- Field names must match exact names from AdCP schema (e.g., `format` not `format_id`)
- All AdCP-required fields must be present and non-null
- Internal/database fields must be excluded from external responses

### Schema Validation
Each model must have AdCP contract tests in `tests/unit/test_adcp_contract.py`

## Mandatory Test Pattern

```python
def test_[model]_adcp_compliance(self):
    """Test that [Model] complies with AdCP [schema-name] schema."""
    # 1. Create model with all required + optional fields
    model = YourModel(...)

    # 2. Test AdCP-compliant response
    adcp_response = model.model_dump()

    # 3. Verify required AdCP fields present
    required_fields = ["field1", "field2"]  # From AdCP spec
    for field in required_fields:
        assert field in adcp_response
        assert adcp_response[field] is not None

    # 4. Verify optional AdCP fields present (can be null)
    optional_fields = ["optional1", "optional2"]  # From AdCP spec
    for field in optional_fields:
        assert field in adcp_response

    # 5. Verify internal fields excluded
    internal_fields = ["tenant_id", "created_at"]  # Not in AdCP spec
    for field in internal_fields:
        assert field not in adcp_response

    # 6. Verify field count matches expectation
    assert len(adcp_response) == EXPECTED_FIELD_COUNT
```

## When Adding New Models

1. ✅ Check AdCP spec at https://adcontextprotocol.org/docs/
2. ✅ Add AdCP compliance test BEFORE implementing model
3. ✅ Use `model_dump()` for external responses, `model_dump_internal()` for database
4. ✅ Test with both minimal and full field sets
5. ✅ Verify no internal fields leak to external responses

## Existing AdCP-Compliant Models

All tested and verified:
- ✅ `Product` - AdCP product schema
- ✅ `Creative` - AdCP creative-asset schema
- ✅ `Format` - AdCP format schema
- ✅ `Principal` - AdCP auth schema
- ✅ `Signal` - AdCP get-signals-response schema
- ✅ `Package` - AdCP package schema
- ✅ `Targeting` - AdCP targeting schema
- ✅ `Budget` - AdCP budget schema
- ✅ `Measurement` - AdCP measurement schema
- ✅ `CreativePolicy` - AdCP creative-policy schema
- ✅ `CreativeStatus` - AdCP creative-status schema
- ✅ `CreativeAssignment` - AdCP creative-assignment schema

## Zero Tolerance Policy

- ❌ **No model can be client-facing without a compliance test**
- ❌ **No PR can merge if it adds client-facing models without tests**
- ❌ **No exceptions for "temporary" or "prototype" models**

## Comprehensive Test Requirements

1. **Field Coverage**: Test all required and optional AdCP fields are present
2. **Field Exclusion**: Test internal fields are excluded from external responses
3. **Field Types**: Test field types match AdCP schema expectations
4. **Field Values**: Test default values and transformations work correctly
5. **Response Structure**: Test overall response structure matches AdCP spec
6. **Enum Validation**: Test enum values match AdCP specification exactly
7. **Nested Object Validation**: Test complex nested objects
8. **Backward Compatibility**: Test property aliases work correctly

## Running Tests

```bash
# Test all AdCP contract compliance (MUST pass before any commit)
uv run pytest tests/unit/test_adcp_contract.py -v

# Test specific model compliance
uv run pytest tests/unit/test_adcp_contract.py::TestAdCPContract::test_signal_adcp_compliance -v

# Run with coverage
uv run pytest tests/unit/test_adcp_contract.py --cov=src.core.schemas --cov-report=html
```

## Development Workflow

1. 🔍 **Before Creating Model**: Check AdCP spec
2. ✏️ **Write Test First**: Add compliance test before implementing model
3. 🏗️ **Implement Model**: Use `model_dump()` and `model_dump_internal()` pattern
4. ✅ **Verify Test Passes**: Ensure all assertions pass
5. 🔄 **Run Full Suite**: Verify no regressions in other tests

## Why This Is Critical

- **Production Failures**: Non-compliant models cause runtime errors and API failures
- **Client Integration Issues**: AdCP clients expect exact schema compliance
- **Data Leakage**: Internal fields exposed to clients create security risks
- **Protocol Violations**: Non-compliant responses break AdCP specification contracts
