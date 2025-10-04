# A2A Server Regression Prevention

## Critical Lesson: Dec 2024

**🚨 CASE STUDY**: Two critical bugs slipped through test coverage that caused production failures.

## Bugs That Reached Production

1. **Agent Card URL Trailing Slash**: URLs ending with `/a2a/` caused redirects that stripped Authorization headers
2. **Function Call Error**: `core_get_signals_tool.fn()` caused 'FunctionTool' object is not callable error

## Root Causes

### Over-Mocking
Tests mocked the very functions that had bugs. Example:
```python
@patch.object(handler, "_handle_get_signals_skill", new_callable=AsyncMock)
def test_skill(self, mock_skill):
    mock_skill.return_value = {"signals": []}
    # Test passes even if core_get_signals_tool.fn() is broken
```

### Skipped Critical Tests
Main A2A endpoints test was completely disabled with `pytest.skip()`.

### Missing HTTP-Level Testing
No validation of actual agent card URL formats or redirect behavior.

## Prevention Measures Implemented

1. **Regression Tests**: `test_a2a_regression_prevention.py` with URL format and function call validation
2. **Pre-commit Hooks**: `a2a-regression-check` and `no-fn-calls` hooks
3. **Function Call Validation**: `test_a2a_function_call_validation.py` tests imports without excessive mocking
4. **Working Endpoints Test**: Replaced skipped test with `test_a2a_endpoints_working.py`

## Key Learnings

### Mock Only External Dependencies
Mock database, APIs, file I/O - **not internal function calls**.

### Test What You Import
If you import a function, test that it's actually callable.

### HTTP-Level Integration Tests
URL formats, redirects, and header behavior can't be unit tested.

### Never Skip Critical Tests
Disabled tests accumulate technical debt and hide regressions.

### Static Analysis Helps
Simple pattern matching (`.fn()` calls) catches many bugs.

### Validate Response Formats
Agent card URLs and endpoint responses must match expected patterns.

## Anti-Pattern vs Better Pattern

### ❌ Anti-Pattern (What Caused Bugs)
```python
# This hides import/call errors
@patch.object(handler, "_handle_get_signals_skill", new_callable=AsyncMock)
def test_skill(self, mock_skill):
    mock_skill.return_value = {"signals": []}
    # Test passes even if core_get_signals_tool.fn() is broken
```

### ✅ Better Pattern (What Catches Bugs)
```python
# Test actual function imports and HTTP behavior
def test_core_function_callable(self):
    from src.a2a_server.adcp_a2a_server import core_get_signals_tool
    assert callable(core_get_signals_tool)  # Would catch .fn() bug

@pytest.mark.integration
def test_agent_card_url_format(self):
    response = requests.get("http://localhost:8091/.well-known/agent.json")
    url = response.json()["url"]
    assert not url.endswith("/")  # Would catch trailing slash bug
```

## Testing Requirements

### Function Import Validation
```python
def test_imported_functions_callable(self):
    """Verify all imported functions are actually callable."""
    from src.a2a_server.adcp_a2a_server import (
        core_get_products_tool,
        core_get_signals_tool,
        core_get_targeting_tool
    )
    assert callable(core_get_products_tool)
    assert callable(core_get_signals_tool)
    assert callable(core_get_targeting_tool)
```

### Agent Card URL Format
```python
@pytest.mark.integration
def test_agent_card_url_no_trailing_slash(client):
    """Agent card URLs must not have trailing slashes."""
    response = client.get('/.well-known/agent.json')
    agent_card = response.get_json()
    assert not agent_card['url'].endswith('/')
```

### Standard Endpoints
```python
def test_standard_a2a_endpoints(client):
    """Test all standard A2A endpoints exist."""
    endpoints = ['/.well-known/agent.json', '/agent.json', '/a2a', '/stream']
    for endpoint in endpoints:
        response = client.get(endpoint)
        assert response.status_code != 404
```

## Pre-Commit Hooks

### a2a-regression-check
Validates:
- Agent card URL formats (no trailing slashes)
- Function import/call patterns without excessive mocking
- Runs when A2A server files change

### no-fn-calls
Prevents:
- `.fn()` call patterns that caused production bugs
- Enforces direct function calls instead of FunctionTool wrappers

## Running Tests

```bash
# Run A2A regression tests
uv run pytest tests/integration/test_a2a_regression_prevention.py -v

# Run function call validation
uv run pytest tests/integration/test_a2a_function_call_validation.py -v

# Run working endpoints test
uv run pytest tests/integration/test_a2a_endpoints_working.py -v

# Run pre-commit hooks
pre-commit run a2a-regression-check --all-files
pre-commit run no-fn-calls --all-files
```
