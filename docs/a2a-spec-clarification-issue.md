# GitHub Issue: A2A Artifacts Response Format Needs Clearer Specification

## Issue Title
[Clarification Needed]: Artifacts Response Format Specification and Implementation Guidelines

## Issue Description

While implementing an A2A server for the Advertising Context Protocol (AdCP), I encountered several ambiguities in the artifacts response format specification that make it difficult to ensure compliant implementations.

## Current Understanding vs. Specification Gaps

Based on the [A2A specification](https://a2aproject.github.io/A2A/latest/specification/), artifacts should be structured as:

```json
{
  "artifacts": [{
    "name": "artifact_name",
    "parts": [{
      "kind": "application/json",
      "data": { /* structured data */ }
    }]
  }]
}
```

However, the specification lacks clarity on several implementation details:

## Specific Areas Needing Clarification

### 1. **Field Naming Consistency**
- Should parts use `"kind"` or `"type"` for content type?
- The spec shows `"kind"` but some implementations use `"type"`
- **Recommendation**: Explicitly specify the field name

### 2. **Response Wrapper Structure**
- Should responses include a status wrapper like `{"status": {"state": "completed"}, "artifacts": [...]}`?
- Or just the artifacts array directly?
- **Current ambiguity**: Different sections of the spec suggest different approaches

### 3. **Artifact Naming Guidelines**
- What should the `"name"` field contain for different types of responses?
- Should it be descriptive (`"product_catalog"`) or generic (`"response"`)?
- **Need**: Clear naming conventions for common use cases

### 4. **Data Structure Standards**
- For `"kind": "application/json"`, what should the `"data"` field contain?
- Should it be structured business objects or can it be free-form?
- **Example unclear cases**:
  - Product catalogs: `{"products": [...], "total": N}` vs `[{product1}, {product2}]`
  - Error responses: `{"error": "message"}` vs `{"type": "error", "details": "..."}`

### 5. **Multi-Part Artifact Handling**
- When should multiple parts be used vs. multiple artifacts?
- Are parts guaranteed to maintain order (related to issue #899)?
- **Need**: Clear guidance on when to use multiple parts vs. multiple artifacts

### 6. **Content Type Handling**
- What `"kind"` values are officially supported?
- Should implementations support `"text/plain"`, `"text/markdown"`, etc.?
- **Request**: Comprehensive list of supported content types

## Real-World Implementation Example

In our AdCP A2A server, we're handling queries like:
- "What video ad products do you have available?"
- "Show me targeting options"
- "What are your pricing models?"

We want to return structured data that AI agents can easily parse and use, but we need clear guidance on the response format.

### Current Implementation (seeking validation):
```python
task.artifacts = [{
    "name": "product_catalog",
    "parts": [{
        "kind": "application/json",
        "data": {
            "products": [
                {"id": "video_premium", "name": "Premium Video", "formats": ["video_16x9"]},
                {"id": "display_banner", "name": "Banner Display", "formats": ["display_728x90"]}
            ],
            "total": 2,
            "query": "video ad products"
        }
    }]
}]
```

**Question**: Is this the correct format, or should it be structured differently?

## Proposed Solution

We suggest adding a new section to the specification titled **"Artifacts Response Format Guidelines"** that includes:

1. **Field Specification Table**: Exact field names and types required
2. **Response Examples**: Complete, valid response examples for common scenarios
3. **Naming Conventions**: Recommended artifact names for different use cases
4. **Content Type Registry**: Official list of supported `"kind"` values
5. **Multi-Part Guidelines**: When and how to use multiple parts/artifacts
6. **Error Response Format**: Standardized error artifact structure

## Impact

Clear specification will:
- Improve interoperability between A2A implementations
- Reduce implementation inconsistencies
- Enable better tooling and validation
- Facilitate easier integration for developers

## Related Issues
- #899 - Artifact parts ordering concerns
- #982 - Artifacts in task history integration

Would the maintainers be open to accepting a PR that adds this documentation section to the specification?

---

**Implementation Context**: AdCP A2A Server for advertising inventory and campaign management
**Framework**: python-a2a library
**Priority**: High - blocking compliant implementation
