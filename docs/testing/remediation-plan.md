# Test Coverage Remediation Plan

## Current State Analysis

**Run**: `python scripts/analyze_test_coverage.py`

```
📊 COVERAGE SUMMARY
   Implemented skills: 18
   Tested skills:      0 (effectively 3 with over-mocking)
   Coverage:           0.0% (real: ~17%)

❌ UNTESTED SKILLS (15)
   • get_media_buy_delivery ← CAUSED PRODUCTION BUG
   • update_media_buy
   • update_performance_index
   • list_creative_formats
   • list_authorized_properties
   • sync_creatives
   • list_creatives
   • (and 8 more...)

⚠️  OVER-MOCKING VIOLATIONS (6)
   Tests mock internal handlers, defeating test purpose
```

## Root Cause

**Over-mocking anti-pattern**: Integration tests mock the exact code they should be testing.

```python
# ❌ CURRENT: Mocks the bug
with patch.object(handler, "_handle_create_media_buy_skill"):
    # Bug in _handle_create_media_buy_skill never executes!

# ✅ FIXED: Tests the real code
with patch("src.adapters.get_adapter"), \
     patch("src.core.database.get_db_session"):
    # Real handler code runs, would catch bugs
```

## Multi-Layer Prevention System

### Layer 1: Pre-Commit Hooks (Immediate)

**Status**: ✅ Implemented

- `detect-test-antipatterns`: Catches over-mocking before commit
- `no-excessive-mocking`: Limits total mocks per file (max 10)
- Run manually: `python scripts/detect_test_antipatterns.py <file>`

### Layer 2: Coverage Analysis Tool (On-Demand)

**Status**: ✅ Implemented

```bash
# Run full analysis
python scripts/analyze_test_coverage.py

# Run in CI (fails if issues found)
python scripts/analyze_test_coverage.py --strict
```

Shows:
- Which skills lack tests
- Where over-mocking occurs
- Spec compliance issues

### Layer 3: Proper Integration Tests (In Progress)

**Template for new tests**:

```python
@pytest.mark.asyncio
async def test_SKILL_NAME_integration(self):
    """Test SKILL_NAME with real handler code, minimal mocks."""

    # ✅ Create real handler
    handler = AdCPRequestHandler()

    # ✅ Mock ONLY external dependencies
    with patch("src.adapters.get_adapter") as mock_adapter, \
         patch("src.core.database.get_db_session") as mock_db:

        # Setup mocks for external services
        mock_adapter.return_value = MockAdapter()
        mock_db.return_value = InMemoryDB()

        # ✅ Test real A2A message flow
        message = self.create_message_with_skill("SKILL_NAME", {
            "param1": "value1",  # Use spec-compliant names!
        })

        # ✅ Real handler code runs
        result = await handler.on_message_send(message)

        # ✅ Verify end-to-end behavior
        assert result.status == TaskStatus.completed
```

### Layer 4: CI Integration (TODO)

Add to GitHub Actions:

```yaml
# .github/workflows/test.yml
- name: Check test coverage
  run: python scripts/analyze_test_coverage.py --strict

- name: Run integration tests
  run: uv run pytest tests/integration/test_a2a_skill_invocation.py -v
```

## Remediation Checklist

### Phase 1: Fix Existing Tests (Week 1)

- [ ] **Remove over-mocking from 6 locations**
  - [ ] Line 265: `test_natural_language_get_products`
  - [ ] Line 317: `test_explicit_skill_get_products`
  - [ ] Line 369: `test_explicit_skill_create_media_buy`
  - [ ] Line 408: `test_explicit_skill_get_products_a2a_spec`
  - [ ] Lines 462-463: `test_multiple_skill_invocations`

**For each test**:
```python
# Before:
with patch.object(handler, "_handle_get_products_skill"):
    mock_skill.return_value = {...}

# After:
with patch("src.core.database.get_db_session"), \
     patch("src.adapters.get_adapter"):
    # Real handler code runs
```

### Phase 2: Add Missing Critical Tests (Week 1)

**Priority 1** (Caused production bugs):
- [ ] `test_get_media_buy_delivery_spec_compliant()` ← CAUSED BUG
- [ ] `test_get_media_buy_delivery_backward_compatible()`

**Priority 2** (Core AdCP endpoints):
- [ ] `test_update_media_buy_integration()`
- [ ] `test_update_performance_index_integration()`
- [ ] `test_list_creative_formats_integration()`
- [ ] `test_list_authorized_properties_integration()`

**Priority 3** (Creative management):
- [ ] `test_sync_creatives_integration()`
- [ ] `test_list_creatives_integration()`

**Priority 4** (Complete coverage):
- [ ] All remaining 7 untested skills

### Phase 3: Update Documentation (Week 1)

- [ ] Update `docs/testing/` with:
  - [ ] "How to write integration tests" guide
  - [ ] Anti-pattern examples (over-mocking)
  - [ ] Template for A2A skill tests
- [ ] Add to `CLAUDE.md`:
  - [ ] Link to test coverage analysis tool
  - [ ] Requirement: Run before submitting PR
- [ ] Update `docs/CONTRIBUTING.md`:
  - [ ] New skill? Add test!
  - [ ] Pre-commit hooks explanation

### Phase 4: CI Enforcement (Week 2)

- [ ] Add coverage analysis to GitHub Actions
- [ ] Require 100% A2A skill coverage for PRs
- [ ] Add test coverage badge to README
- [ ] Block merges with over-mocking violations

## Testing Principles (Refresher)

From our own `CLAUDE.md` that we need to follow better:

### 1. Less Mocking ≠ Worse Tests
> **Over-mocking hides real bugs**

- Mock external I/O: ✅ Database, HTTP, adapters
- Mock internal logic: ❌ Handlers, implementations

### 2. Integration Tests Matter
> **HTTP-level behavior can't be unit tested**

- Test the full request → handler → core → response path
- Use real Pydantic models, not mock dicts
- Verify actual serialization, not just logic

### 3. Test What You Import
> **If you import it, test that it works**

- We import `get_principal_from_context` everywhere
- But never tested it with `ToolContext`
- Result: Production bug

## Quick Reference Commands

```bash
# Analyze coverage and anti-patterns
python scripts/analyze_test_coverage.py

# Test specific skills
uv run pytest tests/integration/test_a2a_skill_invocation.py::TestA2ASkillInvocation::test_get_media_buy_delivery_integration -v

# Run all integration tests
uv run pytest tests/integration/ -v

# Check for anti-patterns before commit
python scripts/detect_test_antipatterns.py tests/integration/test_a2a_skill_invocation.py

# Pre-commit hooks
pre-commit run --all-files
```

## Success Criteria

✅ **Coverage**: 100% of AdCP skills have integration tests
✅ **Anti-patterns**: Zero over-mocking violations
✅ **Spec compliance**: All tests use spec-compliant parameter names
✅ **CI**: Coverage analysis runs automatically
✅ **Documentation**: Updated with clear examples

## Timeline

- **Week 1**: Fix existing tests + add critical missing tests
- **Week 2**: Complete coverage + CI integration
- **Ongoing**: Pre-commit hooks enforce standards

## Owner

Engineering team - assign specific skills to developers

## Questions?

Run: `python scripts/analyze_test_coverage.py`
See: `docs/testing/integration-test-guide.md` (to be created)
Ask: #engineering Slack channel
