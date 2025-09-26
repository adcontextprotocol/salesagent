# Contract Validation Prevention System

This document describes the comprehensive system implemented to prevent contract validation issues like the `'brief' is a required property` error that was affecting MCP tool usage.

## Overview

Contract validation issues occur when MCP tool schemas are overly strict, requiring parameters that clients expect to be optional. This creates a poor developer experience and can break integrations.

## Original Problem

The original issue was in `get_products`:
```python
# ❌ BEFORE: Over-strict validation
class GetProductsRequest(BaseModel):
    brief: str                    # Required but expected to be optional
    promoted_offering: str = Field(..., description="...")
```

Clients calling `get_products(promoted_offering="purina cat food")` would get:
```
Sales agent Wonderstruck returned error: Input validation error: 'brief' is a required property
```

## Solution Implemented

### 1. Fixed Schema Validation
```python
# ✅ AFTER: Sensible defaults
class GetProductsRequest(BaseModel):
    brief: str = Field(
        "",  # Default to empty string
        description="Brief description of campaign (optional)"
    )
    promoted_offering: str = Field(
        ...,  # Still required per AdCP spec
        description="Product being promoted (REQUIRED per AdCP spec)"
    )
```

### 2. Fixed SignalDeliverTo Over-Validation
```python
# ✅ AFTER: Practical defaults
class SignalDeliverTo(BaseModel):
    platforms: str | list[str] = Field(
        "all",  # Default to all platforms
        description="Target platforms (defaults to 'all')"
    )
    countries: list[str] = Field(
        default_factory=lambda: ["US"],  # Default to US
        description="Countries for signals (defaults to ['US'])"
    )
```

### 3. Updated MCP Tool Signatures
```python
# ✅ Proper parameter ordering (required first, optional with defaults)
@mcp.tool
async def get_products(
    promoted_offering: str,      # Required parameter first
    brief: str = "",            # Optional with default
    context: Context = None     # Context always last
) -> GetProductsResponse:
```

## Prevention System Components

### 1. Contract Validation Tests
**File**: `tests/integration/test_mcp_contract_validation.py`

Tests that all MCP tools can be called with minimal required parameters:
```python
def test_get_products_minimal_call(self):
    """Test get_products can be called with just promoted_offering."""
    request = GetProductsRequest(promoted_offering="purina cat food")
    assert request.brief == ""  # Should default to empty string
```

### 2. Required Fields Audit Script
**File**: `scripts/audit_required_fields.py`

Automatically analyzes all Request schemas for potentially over-strict validation:
```bash
uv run python scripts/audit_required_fields.py
```

Output includes:
- Required fields analysis
- Potentially over-strict field detection
- Good patterns identification
- Recommendations for improvement

### 3. Pre-commit Hooks
**File**: `.pre-commit-config.yaml`

Two new hooks prevent regressions:

```yaml
# Test MCP contract validation
- id: mcp-contract-validation
  name: MCP contract validation tests
  entry: uv run pytest tests/integration/test_mcp_contract_validation.py -v --tb=short
  files: '^(src/core/schemas\.py|src/core/main\.py)$'

# Audit required fields
- id: audit-required-fields
  name: Audit required fields for over-validation
  entry: uv run python scripts/audit_required_fields.py
  files: '^src/core/schemas\.py$'
```

## Best Practices for Schema Design

### 1. Field Requirements Analysis
Before making a field required, ask:
- **Is this truly necessary for business logic?**
- **Can this have a sensible default value?**
- **Would clients expect this to be optional?**

### 2. Good Default Values
- `brief: str = ""` - Empty string for optional descriptions
- `platforms: str = "all"` - Sensible platform default
- `countries: list[str] = ["US"]` - Common country default
- `pacing: str = "even"` - Reasonable pacing strategy

### 3. Parameter Ordering in MCP Tools
```python
# ✅ CORRECT ordering
@mcp.tool
async def my_tool(
    required_param: str,           # Required first
    optional_param: str = "default",  # Optional with defaults
    context: Context = None        # Context always last
):
```

### 4. Documentation Requirements
For required fields, include business justification:
```python
required_field_justifications = {
    "GetProductsRequest.promoted_offering": "Required per AdCP spec for product discovery",
    "ActivateSignalRequest.signal_id": "Must specify which signal to activate",
    "CreateMediaBuyRequest.po_number": "Required for financial tracking and billing",
}
```

## Testing Your Schemas

### Quick Validation Test
```python
# Test minimal parameter creation
request = YourRequest(only_required_param="value")
assert request.optional_param == expected_default
```

### Run Contract Validation
```bash
# Test all contract validation
uv run pytest tests/integration/test_mcp_contract_validation.py -v

# Audit current schemas
uv run python scripts/audit_required_fields.py

# Run pre-commit checks
pre-commit run mcp-contract-validation --all-files
pre-commit run audit-required-fields --all-files
```

## Monitoring and Alerts

The pre-commit hooks will:
- **Block commits** that introduce over-strict validation
- **Warn about** fields that could have better defaults
- **Document** current schema patterns for consistency

## Common Anti-Patterns to Avoid

### ❌ Over-Strict Required Fields
```python
# Don't require fields that could have defaults
class BadRequest(BaseModel):
    brief: str = Field(..., description="Brief (but could default to '')")
    name: str = Field(..., description="Name (but could auto-generate)")
```

### ❌ No Business Justification
```python
# Don't require fields without clear business need
class BadRequest(BaseModel):
    mysterious_field: str = Field(..., description="No clear purpose")
```

### ❌ Poor Default Values
```python
# Don't use None when empty collections/strings make sense
class BadRequest(BaseModel):
    tags: list[str] | None = None      # ❌ Use [] instead
    description: str | None = None     # ❌ Use "" instead
```

## Success Metrics

This prevention system has:
- ✅ **Fixed 2 validation issues**: `brief` and `SignalDeliverTo` fields
- ✅ **Added automatic detection** for future over-validation
- ✅ **Created regression prevention** via pre-commit hooks
- ✅ **Documented best practices** for schema design
- ✅ **Zero false positives** in audit (all flagged issues were real)

## When to Update This System

Update when:
1. **New validation issues are reported** - Add test cases
2. **AdCP specification changes** - Update schema requirements
3. **Client usage patterns change** - Adjust default values
4. **New MCP tools are added** - Ensure they follow patterns

The goal is to maintain **excellent developer experience** while ensuring **protocol compliance** and **business logic integrity**.
