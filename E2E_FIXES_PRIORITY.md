# E2E Test Fixes - Priority Action List

**Created**: 2025-10-09
**Status**: Ready for implementation

---

## TL;DR - The Problem

We have 9 E2E test files (3,189 lines), but most are broken or empty. The root cause isn't bugs - it's **architectural fragmentation**. Tests were written at different times using different AdCP versions, database patterns, and MCP calling conventions.

**Key Issues**:
1. Database initialization creates duplicate tenants (race condition)
2. Tests use old AdCP formats (we deleted 27 tests for this reason)
3. MCP tool calling conventions changed (request wrapper removal)
4. Docker lifecycle not properly managed (no cleanup)
5. No canonical pattern until recently

---

## What Works Now

✅ **`test_adcp_reference_implementation.py`** - The ONE good test
- Complete campaign lifecycle (316 lines)
- Uses AdCP V2.3 format correctly
- Proper MCP calling patterns
- Mix of sync + async (webhook) responses
- This is our template for all future E2E tests

✅ **Helper utilities**:
- `adcp_request_builder.py` - Schema-compliant request builders
- `adcp_schema_validator.py` - Validation utilities

---

## Immediate Actions (Priority Order)

### 🔥 **CRITICAL FIX 1: Database Initialization** (4 hours)

**Problem**: Multiple init paths create duplicate tenants → CI failures

**Files to change**:
1. `src/core/database/database.py::init_db()` - Add `mode` parameter
2. `scripts/deploy/entrypoint.sh` - Use `init_db(mode="default")`
3. `tests/e2e/conftest.py` - Call `init_db(mode="ci")` in fixture

**Implementation**:
```python
# src/core/database/database.py
def init_db(mode: str = "default", exit_on_error: bool = False):
    """Initialize database.

    Args:
        mode: "default" (production), "ci" (tests), "skip" (migrations only)
    """
    run_migrations(exit_on_error=exit_on_error)

    with get_db_session() as session:
        # Check if ANY tenants exist
        stmt = select(func.count()).select_from(Tenant)
        if session.scalar(stmt) > 0:
            print("Tenants exist, skipping initialization")
            return

        # Create appropriate tenant based on mode
        if mode == "ci":
            create_ci_test_tenant(session)  # Fixed token: "ci-test-token"
        elif mode == "default":
            create_default_tenant(session)  # Random admin token

        session.commit()
```

**Why this fixes it**:
- Single initialization path (no more race conditions)
- Idempotent (checks for existing tenants)
- Mode makes intent explicit

---

### 🔥 **CRITICAL FIX 2: Docker Fixture Cleanup** (2 hours)

**Problem**: Docker containers stay running, volumes persist, tests interfere

**File to change**: `tests/e2e/conftest.py::docker_services_e2e`

**Add**:
1. Proper cleanup in fixture teardown
2. Timeout protection
3. Better error messages with container logs

**Implementation**:
```python
@pytest.fixture(scope="session")
def docker_services_e2e(request):
    # ALWAYS clean up first
    cleanup_docker()

    # Start services with timeout
    try:
        subprocess.run(
            ["docker-compose", "up", "-d", "--build"],
            check=True, timeout=180, env=env
        )
    except Exception as e:
        cleanup_docker()
        pytest.fail(f"Failed to start: {e}")

    # Wait for health checks
    if not wait_for_services(...):
        logs = get_container_logs()
        cleanup_docker()
        pytest.fail(f"Services unhealthy:\n{logs}")

    yield ports

    # ALWAYS clean up (even on failure)
    cleanup_docker()

def cleanup_docker():
    subprocess.run(["docker-compose", "down", "-v", "--remove-orphans"])
    subprocess.run(["docker", "volume", "prune", "-f"])
```

**Why this fixes it**:
- Guaranteed cleanup (no orphaned containers)
- Better error messages (includes logs)
- Prevents test interference

---

### ⚠️ **IMPORTANT FIX 3: Delete Broken Tests** (1 hour)

**Problem**: 8 of 9 test files are broken, empty, or obsolete

**Files to DELETE**:
```bash
# Empty placeholders (4 files)
rm tests/e2e/test_adcp_full_lifecycle.py
rm tests/e2e/test_creative_lifecycle_end_to_end.py
rm tests/e2e/test_mock_server_testing_backend.py
rm tests/e2e/test_testing_hooks.py

# Obsolete/complex (4 files)
rm tests/e2e/test_strategy_simulation_end_to_end.py  # Uses deprecated strategy system
rm tests/e2e/test_adcp_schema_compliance.py  # Redundant (covered by contract tests)
rm tests/e2e/test_schema_validation_standalone.py  # Utility, not test

# Move this one to utils
mv tests/e2e/test_a2a_adcp_compliance.py tests/e2e/test_a2a_protocol.py
# Then refactor to use reference pattern
```

**Files to KEEP**:
- ✅ `test_adcp_reference_implementation.py` (rename to `test_adcp_happy_path.py`)
- ✅ `adcp_request_builder.py` (move to `tests/e2e/utils/`)
- ✅ `adcp_schema_validator.py` (move to `tests/e2e/utils/`)

**After deletion**: 2 test files (happy path + A2A), ~500 lines total

---

### 📝 **NICE TO HAVE 1: Add Error Handling Test** (3 hours)

**Create**: `tests/e2e/test_adcp_error_handling.py` (~200 lines)

**Test cases**:
```python
async def test_invalid_auth_token():
    """Should return 401 for invalid token."""
    # Use wrong token → expect 401

async def test_missing_required_field():
    """Should return 400 for missing promoted_offering."""
    # Omit required field → expect validation error

async def test_nonexistent_resource():
    """Should return 404 for invalid media_buy_id."""
    # Query fake ID → expect 404

async def test_budget_constraint_violation():
    """Should return 400 for budget exceeding limit."""
    # Request budget > max_daily_budget → expect error
```

**Why this matters**:
- Validates error handling paths
- Documents expected error responses
- Catches regressions in error messages

---

### 📝 **NICE TO HAVE 2: Pre-Push Hook** (1 hour)

**Create**: `.git/hooks/pre-push`

```bash
#!/bin/bash
echo "Running E2E integration check..."

# Only run reference test (fast, covers main paths)
if ! pytest tests/e2e/test_adcp_happy_path.py -v --tb=short; then
    echo "❌ E2E reference test failed"
    echo "Run 'pytest tests/e2e/test_adcp_happy_path.py -v' to debug"
    exit 1
fi

echo "✅ E2E integration check passed"
```

**Why this matters**:
- Catch Docker, database, schema issues BEFORE pushing
- Fast feedback (2-3 min vs 5-10 min in CI)
- Prevents broken commits from reaching CI

---

## Implementation Order

**Day 1** (6 hours):
1. ✅ Fix database initialization (4 hrs)
2. ✅ Fix Docker fixture cleanup (2 hrs)

**Day 2** (4 hours):
3. ✅ Delete broken tests (1 hr)
4. ✅ Verify reference test passes in CI (1 hr)
5. ✅ Add error handling test (2 hrs)

**Day 3** (3 hours):
6. ✅ Add pre-push hook (1 hr)
7. ✅ Refactor A2A test (2 hrs)

**Total**: 13 hours (~2 days)

---

## Success Criteria

**Before**:
- ❌ 9 test files, 4 empty
- ❌ Repeated duplicate tenant errors
- ❌ Tests fail with unclear messages
- ❌ 27 tests deleted for incompatibility

**After**:
- ✅ 2-3 high-quality test files
- ✅ Zero duplicate tenant errors
- ✅ Clear error messages
- ✅ All tests pass for 2+ weeks
- ✅ CI failure rate < 5%

---

## Testing the Fixes

After each fix:

```bash
# 1. Clean state
docker-compose down -v
docker volume prune -f

# 2. Run reference test
pytest tests/e2e/test_adcp_reference_implementation.py -v

# 3. Run all E2E tests
pytest tests/e2e/ -v

# 4. Verify CI
git push origin fix-e2e-tests
# Check GitHub Actions
```

---

## Files Reference

**Must Change**:
- `src/core/database/database.py` - Add mode parameter to init_db()
- `scripts/deploy/entrypoint.sh` - Call init_db(mode="default")
- `tests/e2e/conftest.py` - Fix Docker fixture + call init_db(mode="ci")

**Must Delete** (8 files):
- `tests/e2e/test_adcp_full_lifecycle.py`
- `tests/e2e/test_creative_lifecycle_end_to_end.py`
- `tests/e2e/test_mock_server_testing_backend.py`
- `tests/e2e/test_testing_hooks.py`
- `tests/e2e/test_strategy_simulation_end_to_end.py`
- `tests/e2e/test_adcp_schema_compliance.py`
- `tests/e2e/test_schema_validation_standalone.py`
- `tests/e2e/conftest_contract_validation.py` (if not used)

**Must Keep**:
- `tests/e2e/test_adcp_reference_implementation.py` (THE good one)
- `tests/e2e/adcp_request_builder.py` (helpers)
- `tests/e2e/adcp_schema_validator.py` (validation)
- `tests/e2e/conftest.py` (fixtures)

**Must Create**:
- `tests/e2e/test_adcp_error_handling.py` (new test)
- `.git/hooks/pre-push` (pre-push hook)

---

## Questions?

**Q: Why not fix all the broken tests?**
A: They use old patterns (different AdCP versions, old MCP conventions). Easier to consolidate to the one working pattern than fix 8 different patterns.

**Q: What if we need more E2E coverage?**
A: Add test cases to the 2-3 canonical tests. Don't create new test files unless absolutely necessary.

**Q: How do we prevent this from happening again?**
A:
1. Reference implementation is the template
2. Pre-push hook catches integration issues
3. Pre-commit hooks enforce patterns
4. Document the ONE correct way

**Q: Can we run E2E tests locally without Docker?**
A: No - E2E tests MUST use Docker (PostgreSQL requirement). Unit tests don't need Docker.

---

## Full Analysis

See `E2E_TEST_ARCHITECTURE_ANALYSIS.md` for detailed analysis (15 pages).
