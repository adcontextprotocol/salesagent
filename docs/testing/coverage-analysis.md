# Test Coverage Analysis

> **Summary**: Our tests didn't catch two production bugs because of **over-mocking** - mocking the exact functions that contained the bugs, preventing real code execution.

## The Problem

### Bug 1: Authentication Failure in `create_media_buy`

**Root Cause**: `get_principal_from_context()` only handled FastMCP `Context` objects, not `ToolContext` objects passed by A2A server.

**Why Tests Passed**:
```python
# test_a2a_skill_invocation.py
with patch.object(handler, "_handle_create_media_buy_skill") as mock:
    mock.return_value = {"success": True}
    # Bug never executes - we mocked the entire handler!
```

The test mocked `_handle_create_media_buy_skill()` which is the function that:
1. Creates the `ToolContext`
2. Calls `get_principal_from_context()` ← **Bug was here**
3. Never ran real code path

### Bug 2: Spec Compliance for `get_media_buy_delivery`

**Root Cause**: Handler expected `media_buy_id` (singular) but AdCP spec requires `media_buy_ids` (plural).

**Why Tests Didn't Catch It**: **No test existed** for `get_media_buy_delivery` in A2A skill invocation suite.

```python
# Tests exist for:
test_explicit_skill_get_products ✅
test_explicit_skill_create_media_buy ✅

# Missing:
test_explicit_skill_get_media_buy_delivery ❌
```

## Current Coverage Statistics

**Run**: `uv run python scripts/analyze_test_coverage.py`

```
📊 COVERAGE SUMMARY
   Implemented skills: 18
   Tested skills:      3 (17%)
   Coverage:           17%

❌ UNTESTED SKILLS (15)
   • get_media_buy_delivery  ← CAUSED BUG
   • update_media_buy
   • update_performance_index
   • list_creative_formats
   • list_authorized_properties
   • sync_creatives
   • list_creatives
   ... and 8 more

⚠️  OVER-MOCKING VIOLATIONS (6)
   Lines: 265, 317, 369, 408, 462, 463
   All mock internal handlers instead of testing real code
```

## Root Causes

### 1. Over-Mocking Anti-Pattern

```python
# ❌ BAD: Mocks the function containing the bug
with patch.object(handler, "_handle_create_media_buy_skill") as mock:
    mock.return_value = {...}  # Bug never executes

# ✅ GOOD: Mocks only external dependencies
with patch("src.adapters.get_adapter"), \
     patch("src.core.database.get_db_session"):
    # Real handler code runs - would catch bugs!
```

### 2. Incomplete Test Coverage

We tested the "happy path" for some skills but didn't test:
- All AdCP skills (missing 15/18)
- Spec-compliant parameter names
- Real integration paths (A2A → Core → Database)

### 3. Mocking at Wrong Abstraction Level

```
Test Layer      What We Mocked         What We Should Mock
─────────────────────────────────────────────────────────────
Unit Tests      Skill handlers ❌      Database, HTTP clients ✅
Integration     Skill handlers ❌      Only external services ✅
E2E             Nothing ✅             Nothing ✅
```

## Analysis Tools

### 1. Coverage Analysis Tool

**Location**: `scripts/analyze_test_coverage.py`

**Usage**:
```bash
# Run analysis
uv run python scripts/analyze_test_coverage.py

# Strict mode (fails on issues - for CI)
uv run python scripts/analyze_test_coverage.py --strict
```

**Output**:
- Lists all 18 implemented AdCP skills
- Shows which have tests (3/18)
- Identifies over-mocking violations with line numbers
- Reports coverage percentage
- Shows spec compliance issues

### 2. Anti-Pattern Detection

**Location**: `scripts/detect_test_antipatterns.py`

**Usage**:
```bash
# Check specific file
uv run python scripts/detect_test_antipatterns.py tests/integration/test_foo.py

# Runs automatically as pre-commit hook
git commit  # Hook runs automatically
```

**Detects**:
- `patch.object(handler, "_handle_*")` in integration tests
- `patch("src.core.main._*_impl")` internal mocking
- Missing tests for new skill handlers

## Lessons Learned

### 1. Follow Our Own "Less Mocking" Philosophy

From `CLAUDE.md`:
> **Less Mocking ≠ Worse Tests**: Over-mocking hides real bugs

We documented this principle but didn't follow it in these tests.

### 2. Test What You Import

From our testing philosophy:
> **Test What You Import**: If you import it, test that it works

We import `get_principal_from_context` everywhere but never tested it with `ToolContext`.

### 3. Integration Tests Should Test Real Paths

```python
# ❌ BAD: Mock internal handler
with patch.object(handler, "_handle_create_media_buy_skill"):
    pass  # Real code never runs

# ✅ GOOD: Mock only external I/O
with patch("src.adapters.get_adapter"), \
     patch("src.core.database.get_db_session"):
    # Real handler code runs - would catch bugs
```

## Prevention Measures Implemented

### Layer 1: Pre-Commit Hook
✅ Detects over-mocking before commit
✅ Warns about untested skill handlers
✅ Runs automatically on every commit

### Layer 2: Coverage Analysis Tool
✅ Shows coverage gaps (15/18 untested)
✅ Identifies over-mocking locations
✅ Can run in strict mode for CI

### Layer 3: Documentation
✅ Complete guide: [preventing-over-mocking.md](preventing-over-mocking.md)
✅ Test templates with correct patterns
✅ Examples of what to mock vs not mock

### Layer 4: Remediation Plan
✅ Step-by-step plan: [remediation-plan.md](remediation-plan.md)
✅ Timeline and ownership
✅ Success criteria

## See Also

- [preventing-over-mocking.md](preventing-over-mocking.md) - How to write proper tests
- [remediation-plan.md](remediation-plan.md) - Action plan to fix coverage
- [postmortems/2025-10-04-test-agent-auth-bug.md](postmortems/2025-10-04-test-agent-auth-bug.md) - Detailed incident report
