# Fix: A2A get_products brand_manifest Parameter Support

## Problem

The A2A server's `get_products` skill handler was not extracting the `brand_manifest` parameter from skill invocations, causing validation errors when clients tried to use the new AdCP-compliant `brand_manifest` parameter instead of the deprecated `promoted_offering`.

### Error Message
```
"brand_manifest must provide brand information"
```

### Root Cause

In `src/a2a_server/adcp_a2a_server.py`, the `_handle_get_products_skill()` method only extracted `brief` and `promoted_offering` parameters, but did not extract:
- `brand_manifest`
- `filters`
- `min_exposures`
- `adcp_version`
- `strategy_id`

This meant that when clients called:
```python
result = await test_agent.simple.get_products(
    brand_manifest={'name': 'Nike', 'url': 'https://nike.com'},
    brief='Athletic footwear'
)
```

The A2A server would call the core `get_products_tool` without passing `brand_manifest`, triggering the validation error.

## Solution

Updated `_handle_get_products_skill()` to extract and pass all AdCP-compliant parameters:

### Changes in `src/a2a_server/adcp_a2a_server.py`

```python
async def _handle_get_products_skill(self, parameters: dict, auth_token: str) -> dict:
    # Map A2A parameters to GetProductsRequest
    brief = parameters.get("brief", "")
    promoted_offering = parameters.get("promoted_offering", "")
    brand_manifest = parameters.get("brand_manifest", None)  # NEW
    filters = parameters.get("filters", None)  # NEW
    min_exposures = parameters.get("min_exposures", None)  # NEW
    adcp_version = parameters.get("adcp_version", "1.0.0")  # NEW
    strategy_id = parameters.get("strategy_id", None)  # NEW

    # Require either brand_manifest OR promoted_offering (backward compat)
    if not brief and not promoted_offering and not brand_manifest:
        raise ServerError(
            InvalidParamsError(
                message="Either 'brand_manifest', 'promoted_offering', or 'brief' parameter is required"
            )
        )

    # Call core function with all parameters
    response = await core_get_products_tool(
        brief=brief,
        promoted_offering=promoted_offering,
        brand_manifest=brand_manifest,  # NEW
        filters=filters,  # NEW
        min_exposures=min_exposures,  # NEW
        adcp_version=adcp_version,  # NEW
        strategy_id=strategy_id,  # NEW
        context=self._tool_context_to_mcp_context(tool_context),
    )
```

## Backward Compatibility

The fix maintains backward compatibility:

1. **Deprecated `promoted_offering`** - Still works for legacy clients
2. **Brief-only calls** - Still work (brief is used as fallback for promoted_offering)
3. **New `brand_manifest`** - Now properly supported per AdCP spec

## Testing

Added comprehensive unit tests in `tests/unit/test_a2a_brand_manifest_parameter.py`:

- ✅ `test_handle_get_products_skill_extracts_brand_manifest()` - Dict format
- ✅ `test_handle_get_products_skill_extracts_all_parameters()` - All optional params
- ✅ `test_handle_get_products_skill_backward_compat_promoted_offering()` - Backward compat
- ✅ `test_handle_get_products_skill_brand_manifest_url_string()` - URL string format

All tests pass, verifying the fix works correctly.

## Usage Examples

### With brand_manifest (dict)
```python
result = await agent.simple.get_products(
    brand_manifest={'name': 'Nike', 'url': 'https://nike.com'},
    brief='Athletic footwear'
)
```

### With brand_manifest (URL string)
```python
result = await agent.simple.get_products(
    brand_manifest='https://nike.com',
    brief='Athletic footwear'
)
```

### With filters and min_exposures
```python
result = await agent.simple.get_products(
    brand_manifest={'name': 'Nike'},
    brief='Athletic footwear',
    filters={'delivery_type': 'guaranteed'},
    min_exposures=10000
)
```

### Backward compatible (deprecated)
```python
result = await agent.simple.get_products(
    promoted_offering='Nike Athletic Footwear',
    brief='Display ads'
)
```

## Files Changed

- `src/a2a_server/adcp_a2a_server.py` - Updated `_handle_get_products_skill()` method
- `tests/unit/test_a2a_brand_manifest_parameter.py` - New unit tests
- `tests/integration_v2/test_a2a_brand_manifest.py` - New integration tests

## Related Issues

- AdCP spec requires `brand_manifest` for product discovery
- Test agent in production was configured with public product catalog
- Previous implementation only supported deprecated `promoted_offering` parameter
