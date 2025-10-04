# Preventing Over-Mocking in Tests

## The Problem

Our tests didn't catch two production bugs because of **over-mocking** - mocking the exact functions that contained the bugs.

### Example: Authentication Bug

```python
# ❌ TEST: Mocked the buggy function
with patch.object(handler, "_handle_create_media_buy_skill") as mock:
    mock.return_value = {"success": True}  # Bug never executes!

# The bug was inside _handle_create_media_buy_skill()
# Mocking it meant the test never ran the real code
```

## Solution: Multi-Layer Prevention

### Layer 1: Pre-Commit Hook

**Automatic detection on every commit**

```bash
# Runs automatically on `git commit`
# Can also run manually:
uv run python scripts/detect_test_antipatterns.py tests/integration/test_my_test.py
```

**What it catches**:
- ❌ `patch.object(handler, "_handle_*")` in integration tests
- ❌ `patch("src.core.main._*_impl")` in integration tests
- ⚠️  Missing tests for new skill handlers

### Layer 2: Coverage Analysis Tool

**On-demand comprehensive analysis**

```bash
# Run full analysis
uv run python scripts/analyze_test_coverage.py

# Strict mode (fails if issues found - good for CI)
uv run python scripts/analyze_test_coverage.py --strict
```

**What it reports**:
- 📊 Test coverage percentage
- ❌ Untested skills (all 18 AdCP skills)
- ⚠️  Over-mocking violations (file + line number)
- ⚠️  Spec compliance issues

### Layer 3: Testing Guidelines

## What to Mock

### ✅ DO Mock: External Dependencies

**Database**:
```python
with patch("src.core.database.get_db_session") as mock_db:
    mock_db.return_value = InMemoryDB()
```

**Adapters (external ad servers)**:
```python
with patch("src.adapters.get_adapter") as mock_adapter:
    mock_adapter.return_value = MockGAMAdapter()
```

**HTTP clients**:
```python
with patch("httpx.AsyncClient") as mock_http:
    mock_http.post.return_value = MockResponse()
```

### ❌ DON'T Mock: Internal Functions

**Internal handlers**:
```python
# ❌ BAD: Defeats the test
with patch.object(handler, "_handle_create_media_buy_skill"):
    pass  # Real code never runs!

# ✅ GOOD: Tests real code
# Just don't mock it! Let it run.
```

**Internal implementations**:
```python
# ❌ BAD: Mocks the implementation
with patch("src.core.main._create_media_buy_impl"):
    pass  # Business logic never runs!

# ✅ GOOD: Let real implementation run
# Mock only its external dependencies
```

**Context functions**:
```python
# ❌ BAD: Mocks auth check
with patch("src.core.tools.get_principal_from_context"):
    pass  # Auth bug hidden!

# ✅ GOOD: Pass real ToolContext
context = ToolContext(principal_id="test", ...)
# Real auth code runs
```

## Test Template

### Integration Test (Recommended)

```python
import pytest
from unittest.mock import patch, MagicMock

from src.a2a_server.adcp_a2a_server import AdCPRequestHandler
from src.core.tool_context import ToolContext

class TestA2ASkillIntegration:
    """Integration tests for A2A skills with minimal mocking."""

    @pytest.mark.asyncio
    async def test_SKILL_NAME_integration(self):
        """Test SKILL_NAME with real handler code."""

        # ✅ Create real handler
        handler = AdCPRequestHandler()

        # ✅ Mock ONLY external dependencies
        with patch("src.adapters.get_adapter") as mock_adapter, \
             patch("src.core.database.get_db_session") as mock_db, \
             patch("src.a2a_server.adcp_a2a_server.get_principal_from_token") as mock_auth:

            # Setup external service mocks
            mock_adapter.return_value = self.create_mock_adapter()
            mock_db.return_value = self.create_in_memory_db()
            mock_auth.return_value = "test_principal"

            # ✅ Test real A2A message flow
            message = Message(
                message_id="test-123",
                role=Role.user,
                parts=[Part(data={
                    "skill": "SKILL_NAME",
                    "input": {
                        "param1": "value1",  # Spec-compliant names!
                    }
                })]
            )

            # ✅ Real handler code runs (would catch bugs!)
            result = await handler.on_message_send(
                MessageSendParams(message=message)
            )

            # ✅ Verify end-to-end behavior
            assert result.status.state == TaskState.completed
            assert result.artifacts is not None
            assert len(result.artifacts) > 0

    def create_mock_adapter(self):
        """Helper to create consistent mock adapter."""
        adapter = MagicMock()
        adapter.create_order.return_value = {"order_id": "test-order"}
        return adapter

    def create_in_memory_db(self):
        """Helper to create in-memory test database."""
        # Use real SQLAlchemy with SQLite :memory:
        from sqlalchemy import create_engine
        engine = create_engine("sqlite:///:memory:")
        # ... setup schema ...
        return engine
```

## Common Mistakes

### Mistake 1: Mocking Too High

```python
# ❌ BAD: Mocks entire skill handler
with patch.object(handler, "_handle_get_products_skill"):
    mock.return_value = {"products": []}

# ✅ GOOD: Mock only database/adapter
with patch("src.core.database.get_db_session"):
    # Real handler runs, only DB is mocked
```

### Mistake 2: Not Testing Real Data Flow

```python
# ❌ BAD: Returns mock dict directly
mock_skill.return_value = {"products": [...]}

# ✅ GOOD: Tests real Pydantic serialization
# Let real code return GetProductsResponse
# Verify response.model_dump() works correctly
```

### Mistake 3: Skipping Spec Compliance

```python
# ❌ BAD: Uses non-spec parameter name
skill_params = {"media_buy_id": "123"}  # Singular!

# ✅ GOOD: Uses spec-compliant name
skill_params = {"media_buy_ids": ["123"]}  # Plural per AdCP v1.6.0
```

## Running the Checks

### Before Committing

```bash
# Check your test file
uv run python scripts/detect_test_antipatterns.py tests/integration/test_my_new_test.py

# Should output:
✅ No anti-patterns detected
```

### Before Creating PR

```bash
# Full coverage analysis
uv run python scripts/analyze_test_coverage.py

# Should show:
📊 Coverage: 100%
✅ No untested skills
✅ No over-mocking violations
```

### During Code Review

**Reviewer checklist**:
- [ ] New skill handler has corresponding test?
- [ ] Test mocks only external dependencies?
- [ ] Test uses spec-compliant parameter names?
- [ ] Coverage analysis shows 100%?

## Philosophy

From our testing guidelines in `CLAUDE.md`:

> **1. Less Mocking ≠ Worse Tests**
> Over-mocking hides real bugs. Mock external I/O, not internal logic.

> **2. Integration Tests Matter**
> HTTP-level behavior can't be unit tested. Test full request → response.

> **3. Test What You Import**
> If you import it, test that it works. Don't mock it away.

## Tools Reference

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `analyze_test_coverage.py` | Coverage analysis | Before PR, during sprint planning |
| `detect_test_antipatterns.py` | Anti-pattern detection | Automatic (pre-commit hook) |
| `pre-commit run --all-files` | Run all checks | Before pushing |
| `pytest tests/integration/ -v` | Run integration tests | After fixing tests |

## Questions?

- **"How do I test without mocking X?"**
  → Use real in-memory SQLite, real Pydantic models

- **"But the test is slow with real DB!"**
  → SQLite :memory: is fast. Real bugs > fast tests.

- **"What if I need to test error handling?"**
  → Mock the external service to return errors, but let real handler code process them

- **"Can I ever mock internal functions?"**
  → Only in pure unit tests. Never in integration tests.

## See Also

- `TEST_COVERAGE_ANALYSIS.md` - Why tests didn't catch bugs
- `TEST_COVERAGE_REMEDIATION_PLAN.md` - Fixing existing tests
- `docs/testing/integration-test-guide.md` - Complete guide (TODO)
