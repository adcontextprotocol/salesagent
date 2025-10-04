# MCP Tool Roundtrip Validation

## Critical Lesson: Sep 2025

**🚨 CASE STUDY**: A "formats field required" validation error reached production in the `get_products` MCP tool due to inadequate roundtrip conversion testing.

## The Issue

MCP tools use a critical roundtrip conversion pattern:

```python
# Pattern that was failing in production:
response_data = {"products": [p.model_dump_internal() for p in eligible_products]}
response_data = apply_testing_hooks(response_data, testing_ctx, "get_products")
modified_products = [Product(**p) for p in response_data["products"]]  # FAILED HERE
```

## Root Cause

Tests used mock dictionaries instead of real Product objects, missing the fact that our Pydantic models use internal field names (`formats`) while AdCP spec requires external names (`format_ids`).

### Why Tests Missed This

- **Mock Dictionary Data**: `{"products": [{"id": "test", "name": "Test Product"}]}` bypassed Pydantic validation
- **Isolated Schema Tests**: Schema validation tests were separate from actual MCP tool execution
- **Missing Integration**: No tests of the complete flow: Database → Product objects → Testing hooks → Reconstruction

## Prevention Measures Implemented

1. **Roundtrip Validation Tests**: `tests/integration/test_mcp_tool_roundtrip_validation.py` tests actual MCP execution paths
2. **Schema Contract Tests**: `tests/integration/test_schema_contract_validation.py` ensures AdCP compliance after conversions
3. **Reusable Patterns**: `tests/integration/test_schema_roundtrip_patterns.py` provides `SchemaRoundtripValidator`
4. **Fixed Original Test**: `test_mock_server_response_headers.py` now uses real Product objects

## Mandatory Testing Pattern for MCP Tools

```python
# ✅ CORRECT: Test with real objects and actual roundtrip conversion
def test_mcp_tool_roundtrip_validation(self):
    # 1. Create real Product object with internal field names
    product = Product(
        product_id="test",
        formats=["display_300x250"],  # Internal field name
        delivery_type="non_guaranteed",
        is_fixed_price=False
    )

    # 2. Convert to internal dict (preserves field names for roundtrip)
    product_dict = product.model_dump_internal()

    # 3. Apply testing hooks (simulates production path)
    response_data = {"products": [product_dict]}
    response_data = apply_testing_hooks(response_data, testing_ctx, "get_products")

    # 4. Test reconstruction (this was failing in production)
    modified_products = [Product(**p) for p in response_data["products"]]

    # 5. Verify successful roundtrip
    assert modified_products[0].formats == ["display_300x250"]

    # 6. Verify external compliance (for final API response)
    external_dict = product.model_dump()  # Converts formats → format_ids
    assert "format_ids" in external_dict
    assert "formats" not in external_dict
```

## Key Learnings

- **Test Real Data Flows**: Use actual Pydantic objects, not mock dictionaries
- **Exercise Complete Paths**: Test full MCP tool execution, not isolated components
- **Validate Both Internal and External**: Test both roundtrip conversion and AdCP compliance
- **Schema Field Mapping**: Internal field names vs External field names must be tested

## Anti-Patterns to Avoid

```python
# ❌ WRONG: Mock dictionary bypasses validation
response_data = {"products": [{"id": "test", "name": "Test"}]}

# ✅ CORRECT: Real Pydantic objects
product = Product(product_id="test", name="Test", formats=["display_300x250"])
response_data = {"products": [product.model_dump_internal()]}
```

## Running Roundtrip Tests

```bash
# Run MCP roundtrip validation tests
uv run pytest tests/integration/test_mcp_tool_roundtrip_validation.py -v

# Run schema contract tests
uv run pytest tests/integration/test_schema_contract_validation.py -v

# Test all integration patterns
uv run pytest tests/integration/test_schema_roundtrip_patterns.py -v
```
