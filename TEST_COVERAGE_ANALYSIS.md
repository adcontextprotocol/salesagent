# Why Our Tests Didn't Catch These Issues

## Executive Summary
Our tests didn't catch the authentication and spec compliance issues because of **over-mocking** - we mocked the exact functions that contained the bugs, bypassing the real code paths that would have failed.

## Issue 1: Authentication Failure in `create_media_buy`

### What Was Broken
`get_principal_from_context()` only handled FastMCP `Context` objects, not `ToolContext` objects passed by A2A server.

### Why Tests Passed
```python
# test_a2a_skill_invocation.py line ~300
async def test_explicit_skill_create_media_buy(self, handler, mock_principal_context):
    # Mock authentication token
    handler._get_auth_token = MagicMock(return_value="test_token")

    # THIS IS THE PROBLEM: We mock the entire skill handler
    with patch.object(handler, "_handle_create_media_buy_skill",
                     new_callable=AsyncMock) as mock_skill:
        mock_skill.return_value = {...}  # Mock response
```

**The problem**: We mocked `_handle_create_media_buy_skill()` which is the function that:
1. Creates the `ToolContext`
2. Calls `core_create_media_buy_tool()`
3. Eventually calls `get_principal_from_context()` where the bug was

By mocking at this level, we **never executed the real code** that contained the bug.

### What We Should Have Done
```python
# Option 1: Don't mock the skill handler - let real code run
async def test_explicit_skill_create_media_buy(self, handler):
    # Mock only external dependencies (database, adapters)
    with patch("src.core.database.get_db_session"), \
         patch("src.adapters.get_adapter"):
        # Let real code run - would have caught the bug
        result = await handler.on_message_send(params)

# Option 2: Integration test with real A2A server
async def test_a2a_create_media_buy_integration():
    # Start real A2A server
    # Make HTTP request
    # Would have caught the bug
```

## Issue 2: Spec Compliance for `get_media_buy_delivery`

### What Was Broken
A2A handler expected `media_buy_id` (singular) but AdCP spec requires `media_buy_ids` (plural).

### Why Tests Didn't Catch It
We have **no tests** for `get_media_buy_delivery` in A2A skill invocation suite:

```python
# test_a2a_skill_invocation.py has tests for:
- test_explicit_skill_get_products ✅
- test_explicit_skill_create_media_buy ✅
- test_explicit_skill_get_signals ✅
# BUT NO TEST FOR:
- test_explicit_skill_get_media_buy_delivery ❌ MISSING
```

### What We Should Have Done
```python
@pytest.mark.asyncio
async def test_explicit_skill_get_media_buy_delivery_spec_compliant(
    self, handler, mock_principal_context
):
    """Test get_media_buy_delivery accepts plural media_buy_ids per spec."""
    handler._get_auth_token = MagicMock(return_value="test_token")

    # Use spec-compliant parameter name (plural)
    skill_params = {
        "media_buy_ids": ["mb_123", "mb_456"],  # PLURAL per AdCP v1.6.0
        "start_date": "2025-10-01",
        "end_date": "2025-10-31"
    }

    message = self.create_message_with_skill("get_media_buy_delivery", skill_params)
    result = await handler.on_message_send(params)

    # Would have failed with "Missing required parameter: 'media_buy_id'"
```

## Root Causes

### 1. Over-Mocking Anti-Pattern
```python
# ❌ BAD: Mock the function containing the bug
with patch.object(handler, "_handle_create_media_buy_skill") as mock:
    mock.return_value = {...}  # Bug never executes

# ✅ GOOD: Mock only external dependencies
with patch("src.adapters.get_adapter"), \
     patch("src.core.database.get_db_session"):
    # Real code runs, bug would be caught
```

### 2. Incomplete Test Coverage
We tested the "happy path" for some skills but didn't test:
- All AdCP skills (missing `get_media_buy_delivery`)
- Spec-compliant parameter names (plural vs singular)
- Real integration paths (A2A → Core → Database)

### 3. Mocking at Wrong Abstraction Level
```
Test Layer      What We Mocked         What We Should Mock
─────────────────────────────────────────────────────────────
Unit Tests      Skill handlers         Database, HTTP clients
Integration     Skill handlers         Only external services
E2E             Nothing (good!)        Nothing
```

## Lessons Learned

### 1. Follow Our Own "Less Mocking" Philosophy
Our `CLAUDE.md` states:
> **Less Mocking ≠ Worse Tests**: Over-mocking hides real bugs

But we violated this by mocking `_handle_create_media_buy_skill()`.

### 2. Test What You Import
From our testing philosophy:
> **Test What You Import**: If you import it, test that it works

We import `get_principal_from_context` in multiple places but never tested it with `ToolContext`.

### 3. Integration Tests Should Use Real Code Paths
```python
# Current state: Too many mocks
@pytest.fixture
def mock_principal_context(self):
    with patch("get_principal_from_token"), \
         patch("get_current_tenant"):
        yield

# Better: Only mock external I/O
@pytest.fixture
def real_principal_context(self):
    # Use real database (SQLite in-memory)
    # Use real ToolContext creation
    # Only mock adapter API calls
```

## Recommended Fixes

### 1. Add Missing Test Coverage
```python
# tests/integration/test_a2a_skill_invocation.py

@pytest.mark.asyncio
async def test_get_media_buy_delivery_spec_compliant(self):
    """Test media_buy_ids (plural) per AdCP v1.6.0."""
    # Test with real handler, minimal mocks

@pytest.mark.asyncio
async def test_get_media_buy_delivery_backward_compatible(self):
    """Test media_buy_id (singular) still works."""
    # Test backward compatibility
```

### 2. Reduce Mocking in Integration Tests
```python
# Instead of:
with patch.object(handler, "_handle_create_media_buy_skill"):

# Do:
with patch("src.adapters.get_adapter") as mock_adapter:
    # Let real handler code run
    # Only mock external dependencies
```

### 3. Add Spec Compliance Tests
```python
# tests/integration/test_adcp_spec_compliance.py

class TestAdCPSpecCompliance:
    """Verify all endpoints match AdCP spec exactly."""

    def test_get_media_buy_delivery_parameters(self):
        """Verify parameter names match spec."""
        from src.core.schemas import GetMediaBuyDeliveryRequest

        # Should accept media_buy_ids (plural)
        req = GetMediaBuyDeliveryRequest(media_buy_ids=["mb_1"])
        assert req.media_buy_ids is not None
```

## Pre-Commit Hook Suggestion

Add a hook to detect over-mocking in integration tests:

```python
# .pre-commit-config.yaml
- id: detect-integration-test-mocking
  name: Prevent mocking internal functions in integration tests
  entry: detect_mock_antipattern.py
  language: python
  files: 'tests/integration/.*\.py$'
```

```python
# detect_mock_antipattern.py
def check_file(filepath):
    with open(filepath) as f:
        content = f.read()

    # Flag mocking of internal skill handlers
    if 'patch.object(handler, "_handle_' in content:
        print(f"❌ {filepath}: Mocking internal handler defeats test purpose")
        return 1

    return 0
```

## Conclusion

These bugs weren't caught because:
1. ✅ **Authentication bug**: Over-mocked the code path containing the bug
2. ✅ **Spec compliance bug**: Never tested `get_media_buy_delivery` at all

**Fix**: Follow our own testing philosophy - less mocking, more real code paths, complete coverage of all AdCP skills.
