# A2A Response Patterns (ADK-Aligned)

**Status**: Implemented and tested
**Last Updated**: 2025-01-21
**Reference**: [ADK PR #238 - A2A Response Format Specification](https://github.com/adcontextprotocol/adcp/pull/238)

## Overview

Our A2A server implementation follows the ADK PR #238 specification for response structure, using the recommended **TextPart + DataPart** pattern for all responses.

## Response Structure

### Mandatory Requirements (✅ Implemented)

1. **DataPart Required**: All A2A responses MUST include at least one `DataPart` containing the task response payload
2. **Last DataPart Authoritative**: When multiple DataParts exist, the last one is considered authoritative
3. **Spec-Compliant Data**: DataPart contains only AdCP spec-defined fields

### Recommended Pattern (✅ Implemented)

**TextPart + DataPart**: Responses include human-readable text and structured data

```python
Artifact(
    artifact_id="result_1",
    name="product_catalog",
    description="Found 5 products matching your requirements.",
    parts=[
        Part(root=TextPart(text="Found 5 products matching your requirements.")),
        Part(root=DataPart(data={"products": [...]})),
    ]
)
```

## Implementation

### Helper Function

All artifact creation uses `_create_artifact_with_text_and_data`:

```python
def _create_artifact_with_text_and_data(
    self,
    artifact_id: str,
    name: str,
    data: dict,
    description: str | None = None,
) -> Artifact:
    """Create artifact with TextPart + DataPart (ADK pattern)."""
    parts = []
    if description:
        parts.append(Part(root=TextPart(text=description)))
    parts.append(Part(root=DataPart(data=data)))

    return Artifact(
        artifact_id=artifact_id,
        name=name,
        description=description,
        parts=parts,
    )
```

### Usage Patterns

#### 1. Explicit Skill Invocation

Extract human-readable messages from response `__str__()` methods:

```python
description = None
if res["success"] and isinstance(artifact_data, dict):
    try:
        response_obj = self._reconstruct_response_object(res["skill"], artifact_data)
        if response_obj and hasattr(response_obj, "__str__"):
            description = str(response_obj)
    except Exception:
        pass

parts = []
if description:
    parts.append(Part(root=TextPart(text=description)))
parts.append(Part(root=DataPart(data=artifact_data)))
```

#### 2. Natural Language Processing

Generate human-readable descriptions based on query type:

```python
product_count = len(result.get("products", []))
description = f"Found {product_count} advertising product{'s' if product_count != 1 else ''} matching your query."
artifact = self._create_artifact_with_text_and_data(
    artifact_id="product_catalog_1",
    name="product_catalog",
    data=result,
    description=description,
)
```

#### 3. Error Responses

Errors follow the same pattern:

```python
error_data = {
    "errors": [
        {"code": "VALIDATION_ERROR", "message": "Invalid product ID"}
    ]
}
description = "Validation failed: Invalid product ID"

artifact = self._create_artifact_with_text_and_data(
    artifact_id="error_1",
    name="validation_error",
    data=error_data,
    description=description,
)
```

## Benefits of This Approach

1. **ADK Compatibility**: Aligns with Google ADK expectations
2. **Human-Readable**: AI clients get clear descriptions
3. **Structured Data**: Clients can parse AdCP responses
4. **Backwards Compatible**: Populates `description` field
5. **Spec Compliant**: DataPart contains only spec fields

## Testing

Comprehensive test coverage in `tests/integration/test_a2a_adk_alignment.py`:

- ✅ All artifacts have at least one DataPart (mandatory)
- ✅ TextPart optional and included with description
- ✅ Recommended pattern implemented
- ✅ Backwards compatibility maintained
- ✅ Error handling follows ADK conventions
- ✅ Natural language responses include TextPart
- ✅ Skill results include TextPart from `__str__()`

## References

- [ADK PR #238 - A2A Response Format Specification](https://github.com/adcontextprotocol/adcp/pull/238)
- ADK Alignment Analysis: `docs/a2a-adk-alignment.md`
- Implementation: `src/a2a_server/adcp_a2a_server.py`
- Tests: `tests/integration/test_a2a_adk_alignment.py`
