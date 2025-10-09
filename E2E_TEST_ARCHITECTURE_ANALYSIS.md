# E2E Test Architecture Analysis & Recommendations

**Date**: 2025-10-09
**Context**: After 27 test deletions and multiple CI failures, analyzing systemic E2E test issues

---

## Executive Summary

The E2E test suite has suffered from **architectural fragmentation**, not implementation bugs. We have:
- **9 active E2E test files** (3,189 total lines)
- **1 reference implementation** that demonstrates the correct pattern
- **Multiple broken tests** using old AdCP formats or invalid patterns
- **Repeated failures** from the same root causes (database init, schema mismatches, import errors)

**Root Cause**: Tests were written at different times using different AdCP versions, database patterns, and MCP calling conventions. There was no enforcement of a canonical pattern.

**Recommended Action**: Consolidate to 2-3 high-quality E2E tests using the reference implementation pattern, delete the rest.

---

## Current State Assessment

### E2E Test Inventory

| Test File | Status | Lines | Issues |
|-----------|--------|-------|--------|
| `test_adcp_reference_implementation.py` | ✅ **GOOD** | 316 | Reference implementation - correct pattern |
| `test_a2a_adcp_compliance.py` | ⚠️ **COMPLEX** | 409 | May use old patterns, needs review |
| `test_adcp_schema_compliance.py` | ⚠️ **COMPLEX** | 388 | Schema validation framework - may be useful |
| `test_strategy_simulation_end_to_end.py` | ❌ **OLD** | 460 | Uses old strategy system (deprecated) |
| `test_schema_validation_standalone.py` | ⚠️ **UTILITY** | 164 | Standalone validator - not E2E test |
| `test_adcp_full_lifecycle.py` | ❌ **EMPTY** | 17 | Placeholder only |
| `test_creative_lifecycle_end_to_end.py` | ❌ **EMPTY** | 6 | Placeholder only |
| `test_mock_server_testing_backend.py` | ❌ **EMPTY** | 6 | Placeholder only |
| `test_testing_hooks.py` | ❌ **EMPTY** | 6 | Placeholder only |

**Supporting Infrastructure**:
- `adcp_request_builder.py` (241 lines) - ✅ GOOD - Schema-compliant request builders
- `adcp_schema_validator.py` (738 lines) - ✅ GOOD - Schema validation utilities
- `conftest.py` (297 lines) - ⚠️ COMPLEX - Fixture management
- `conftest_contract_validation.py` (150 lines) - ⚠️ COMPLEX - Contract validation hooks

### What's Working

✅ **Reference Test Pattern** (`test_adcp_reference_implementation.py`):
```python
# CORRECT PATTERN:
# 1. Use docker_services_e2e fixture (manages Docker Compose lifecycle)
# 2. Use live_server fixture (provides dynamic port URLs)
# 3. Use test_auth_token fixture (returns "ci-test-token")
# 4. Use adcp_request_builder helpers (enforces AdCP V2.3 format)
# 5. Call tools directly via client.call_tool() - NO REQUEST WRAPPERS
# 6. Test complete lifecycle with sync + async (webhook) responses
```

✅ **Request Builder Helpers** (`adcp_request_builder.py`):
- `build_adcp_media_buy_request()` - Enforces AdCP V2.3 structure
- `build_sync_creatives_request()` - Proper schema compliance
- `build_creative()` - Spec-compliant creative objects
- `build_update_media_buy_request()` - Handles oneOf constraints correctly
- `get_test_date_range()` - ISO 8601 date generation

✅ **Database Initialization**:
- `src/core/database/database.py::init_db()` - Safe, idempotent initialization
- Checks for existing tenants before creating default tenant
- Creates CI test principal with fixed token "ci-test-token"
- Only runs migrations if not skipped

---

## Root Causes Identified

### 1. Database Initialization Race Conditions

**Problem**: Multiple database initialization paths create duplicate tenants.

**Evidence**:
- Recent commits: "Fix database initialization duplicate tenant error" (2dd6e72)
- Recent commits: "Make tenant creation idempotent - fix duplicate key error in CI" (779604e)

**Paths**:
1. `scripts/setup/init_database_ci.py` - Creates "CI Test Tenant" (subdomain: "ci-test")
2. `src/core/database/database.py::init_db()` - Creates "Default Publisher" (tenant_id: "default")
3. `entrypoint.sh` - Calls `init_db()` which may conflict with CI init

**Why This Fails**:
- Docker Compose starts with `entrypoint.sh` → calls `init_db()`
- E2E tests may also call database init → duplicate tenant attempts
- Different scripts use different tenant IDs ("default" vs generated UUIDs)

**Solution**:
```python
# ✅ CORRECT: Always check before creating
stmt = select(Tenant).filter_by(subdomain="ci-test")
existing = session.scalars(stmt).first()
if existing:
    print("Tenant exists, skipping creation")
    return existing

# ❌ WRONG: Assume clean database
tenant = Tenant(subdomain="ci-test")
session.add(tenant)  # Will fail if already exists
```

### 2. AdCP Schema Version Mismatches

**Problem**: Tests written at different times use different AdCP versions.

**Evidence**:
- 27 tests deleted due to "legacy AdCP format" (commit 0ed452e)
- Multiple commits fixing AdCP spec compliance (3592c9c, 302aa6d, 07a92ae)
- Schema updates from registry (3603332, df6f4a0, 451ef62)

**Timeline**:
1. **Old format**: Used to wrap params in request objects
2. **AdCP V2.3**: Passes params directly to tools
3. **Recent changes**: Added `push_notification_config`, updated `Budget` schema

**Example of breakage**:
```python
# ❌ OLD (broken after schema update)
await client.call_tool("create_media_buy", {
    "request": {  # NO - Don't wrap in request!
        "product_ids": [...],
        ...
    }
})

# ✅ NEW (AdCP V2.3 format)
await client.call_tool("create_media_buy", {
    "buyer_ref": "...",
    "promoted_offering": "...",  # REQUIRED field
    "packages": [...],
    ...
})
```

### 3. MCP Tool Calling Convention Changes

**Problem**: MCP tool calling patterns changed, breaking tests.

**Evidence**:
- "Remove req wrapper from all MCP tool calls in reference test" (302aa6d)
- "Fix list_creative_formats call in reference E2E test" (07a92ae)

**Old Pattern** (WRONG):
```python
# Wrapped parameters in request object
result = await client.call_tool("tool_name", {
    "request": {
        "param1": "value1",
        "param2": "value2"
    }
})
```

**New Pattern** (CORRECT):
```python
# Pass parameters directly
result = await client.call_tool("tool_name", {
    "param1": "value1",
    "param2": "value2"
})
```

**Why This Matters**:
- FastMCP expects params directly, not wrapped
- Old tests fail with "unexpected keyword argument 'request'"
- Easy to miss during refactoring (no static type checking across MCP boundary)

### 4. Docker Compose Lifecycle Management

**Problem**: Tests assume Docker services are running but don't manage lifecycle properly.

**Evidence**:
- E2E tests start Docker Compose in `conftest.py::docker_services_e2e`
- Wait for health checks (max 120s)
- Dynamic port allocation can conflict with hardcoded ports
- Cleanup not always happening (volumes persist)

**Issues**:
1. **Port conflicts**: If services already running on default ports
2. **Database persistence**: Volumes not cleaned between runs
3. **Initialization timing**: Tests start before database fully initialized
4. **CI vs Local**: Different port configurations

**Current Fixture** (`conftest.py`):
```python
@pytest.fixture(scope="session")
def docker_services_e2e(request):
    # Clean up existing services (good!)
    subprocess.run(["docker-compose", "down", "-v"], capture_output=True)

    # Allocate dynamic ports (good!)
    mcp_port = find_free_port() if not os.getenv("ADCP_SALES_PORT") else ...

    # Start services
    subprocess.run(["docker-compose", "up", "-d", "--build"], check=True, env=env)

    # Wait for health checks (good!)
    max_wait = 120
    while not (mcp_ready and a2a_ready) and time.time() - start_time < max_wait:
        # Poll health endpoints
        ...

    yield ports

    # ⚠️ NO CLEANUP! (teardown code commented out)
```

**Problems**:
- No teardown → Docker services stay running
- Volumes not cleaned → database state persists
- If tests fail during startup, services orphaned

### 5. Test Token Mismatches

**Problem**: Tests use different auth tokens than database provides.

**Evidence**:
- Fixed in multiple commits (alignment of tokens)
- `conftest.py` returns "ci-test-token"
- `init_db()` creates principal with "ci-test-token"
- Old tests may use "test_token_123" or other values

**Correct Pattern**:
```python
# conftest.py
@pytest.fixture
def test_auth_token(live_server):
    # Must match token created by init_db()
    return "ci-test-token"

# database.py::init_db()
ci_test_principal = Principal(
    tenant_id="default",
    principal_id="ci-test-principal",
    access_token="ci-test-token",  # SAME TOKEN
    ...
)
```

---

## Systemic Issues

### Issue 1: No Canonical E2E Pattern Until Recently

**Problem**: Each test file invented its own pattern.

**Evidence**:
- Different fixtures used across tests
- Different database init approaches
- Different MCP calling conventions
- Different AdCP schema versions

**Impact**:
- When patterns changed, all tests broke
- No single source of truth
- Difficult to maintain consistency

**Solution**: Reference implementation now exists (`test_adcp_reference_implementation.py`)

### Issue 2: Infrastructure Complexity Hidden from Developers

**Problem**: E2E tests require complex setup that's not obvious.

**Hidden Requirements**:
1. PostgreSQL database (can't use SQLite)
2. Docker Compose with 3 services (postgres, adcp-server, admin-ui)
3. Database migrations must run
4. Default tenant + principal must exist
5. Correct auth token must be used
6. Ports must be dynamic (or CI-compatible)
7. Health checks must pass before tests run

**Symptoms**:
- Tests fail with cryptic errors ("connection refused", "401 unauthorized", "duplicate key")
- Developers don't know which part of the stack failed
- No clear documentation of dependencies

**Solution**: Better fixture abstraction and error messages

### Issue 3: CI vs Local Environment Differences

**Problem**: Tests pass locally but fail in CI (or vice versa).

**Differences**:

| Aspect | Local | CI |
|--------|-------|-----|
| Ports | Dynamic allocation | Fixed (from env vars) |
| Docker | May use existing containers | Fresh containers |
| Database | May have persisted data | Always clean |
| Timing | Faster (cached images) | Slower (fresh builds) |
| Cleanup | Often skipped | Must be thorough |

**Impact**:
- "Works on my machine" syndrome
- Tests become flaky
- Hard to debug CI failures locally

### Issue 4: Pre-Commit Hooks Can't Catch Integration Issues

**Problem**: Static checks pass but E2E tests fail.

**What Pre-Commit Hooks Check**:
- ✅ Mock count limits
- ✅ AdCP contract compliance (unit tests)
- ✅ MCP minimal param tests
- ✅ No skipped tests

**What They CAN'T Check**:
- ❌ Database initialization works
- ❌ MCP client can connect to server
- ❌ Docker Compose configuration is valid
- ❌ Schema versions match between client and server
- ❌ Import statements resolve correctly

**Example**:
```python
# Pre-commit: PASS ✓ (no syntax errors, imports look fine)
from src.core.tools import get_products_raw

# E2E test: FAIL ✗ (import doesn't exist)
ImportError: cannot import name 'get_products_raw' from 'src.core.tools'
```

---

## Architecture Recommendations

### Recommendation 1: Consolidate to 3 High-Quality E2E Tests

**Goal**: Replace 9 test files with 3 canonical tests.

**Proposed Tests**:

1. **`test_adcp_happy_path.py`** (ALREADY EXISTS as `test_adcp_reference_implementation.py`)
   - Complete campaign lifecycle (discovery → creation → delivery → update)
   - Mix of sync and async (webhook) responses
   - Demonstrates correct MCP calling patterns
   - Uses AdCP V2.3 format with schema helpers
   - ~300 lines

2. **`test_adcp_error_handling.py`** (NEW)
   - Invalid auth token → 401 error
   - Missing required fields → validation error
   - Non-existent media buy ID → 404 error
   - Budget constraints → business rule error
   - ~200 lines

3. **`test_a2a_protocol.py`** (REFACTOR from `test_a2a_adcp_compliance.py`)
   - A2A natural language queries
   - A2A explicit skill invocations
   - Verify AdCP compliance of responses
   - ~200 lines

**Delete**:
- ❌ `test_adcp_full_lifecycle.py` (empty placeholder)
- ❌ `test_creative_lifecycle_end_to_end.py` (empty placeholder)
- ❌ `test_mock_server_testing_backend.py` (empty placeholder)
- ❌ `test_testing_hooks.py` (empty placeholder)
- ❌ `test_strategy_simulation_end_to_end.py` (uses deprecated strategy system)
- ❌ `test_adcp_schema_compliance.py` (covered by contract tests + happy path)

**Keep as Utilities** (move to `tests/e2e/utils/`):
- ✅ `adcp_request_builder.py` (schema helpers)
- ✅ `adcp_schema_validator.py` (validation framework)

### Recommendation 2: Simplify Docker Fixture

**Goal**: Make Docker lifecycle management bulletproof.

**Current Issues**:
- No cleanup in teardown
- Complex port allocation logic
- Health check timeout can cause orphaned containers

**Proposed Fixture**:
```python
@pytest.fixture(scope="session")
def docker_services_e2e(request):
    """Start Docker services with bulletproof cleanup."""

    # 1. ALWAYS clean up first
    cleanup_docker()

    # 2. Use CI ports if set, otherwise use Docker Compose defaults
    #    (Let Docker handle port allocation internally)
    mcp_port = int(os.getenv("ADCP_SALES_PORT", "8092"))
    a2a_port = int(os.getenv("A2A_PORT", "8094"))
    postgres_port = int(os.getenv("POSTGRES_PORT", "5435"))

    # 3. Start services with timeout
    env = {
        "ADCP_SALES_PORT": str(mcp_port),
        "A2A_PORT": str(a2a_port),
        "POSTGRES_PORT": str(postgres_port),
        "ADCP_TESTING": "true",
    }

    try:
        subprocess.run(
            ["docker-compose", "up", "-d", "--build"],
            check=True,
            env=env,
            timeout=180  # 3 min max for startup
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        cleanup_docker()
        pytest.fail(f"Failed to start Docker services: {e}")

    # 4. Wait for health checks with better error messages
    if not wait_for_services(mcp_port, a2a_port, max_wait=120):
        # Get container logs for debugging
        logs = get_container_logs()
        cleanup_docker()
        pytest.fail(f"Services did not become healthy:\n{logs}")

    # 5. Yield ports
    yield {
        "mcp_port": mcp_port,
        "a2a_port": a2a_port,
        "postgres_port": postgres_port
    }

    # 6. ALWAYS clean up (even if test failed)
    cleanup_docker()

def cleanup_docker():
    """Forcefully clean up Docker services and volumes."""
    subprocess.run(["docker-compose", "down", "-v", "--remove-orphans"],
                   capture_output=True, timeout=30)
    subprocess.run(["docker", "volume", "prune", "-f"],
                   capture_output=True, timeout=10)
```

**Benefits**:
- Guaranteed cleanup (even on failure)
- Better error messages (include container logs)
- Simpler port logic (trust Docker Compose)
- Timeout protection (don't hang forever)

### Recommendation 3: Single Database Initialization Path

**Goal**: One function to rule them all.

**Current Problem**:
- `scripts/setup/init_database_ci.py` - CI-specific init
- `src/core/database/database.py::init_db()` - General init
- `entrypoint.sh` - Calls `init_db()` in Docker
- Tests may call either or both

**Proposed Solution**:

```python
# src/core/database/database.py

def init_db(mode: str = "default", exit_on_error: bool = False):
    """Initialize database with multi-tenant support.

    Args:
        mode: Initialization mode
            - "default": Create default tenant (for production/local dev)
            - "ci": Create CI test tenant (for E2E tests)
            - "skip": Skip tenant creation (migrations only)
        exit_on_error: Exit process on error (for scripts)
    """
    # Always run migrations first
    if os.environ.get("SKIP_MIGRATIONS") != "true":
        run_migrations(exit_on_error=exit_on_error)

    with get_db_session() as session:
        # Check what tenants exist
        stmt = select(func.count()).select_from(Tenant)
        tenant_count = session.scalar(stmt)

        if tenant_count > 0:
            print(f"Database has {tenant_count} tenants, skipping initialization")
            return

        # Create tenant based on mode
        if mode == "ci":
            tenant = create_ci_test_tenant(session)
        elif mode == "default":
            tenant = create_default_tenant(session)
        elif mode == "skip":
            print("Skipping tenant creation (mode=skip)")
            return
        else:
            raise ValueError(f"Unknown mode: {mode}")

        session.commit()
        print(f"Created tenant: {tenant.name} (ID: {tenant.tenant_id})")

def create_ci_test_tenant(session) -> Tenant:
    """Create CI test tenant with fixed token for E2E tests."""
    tenant = Tenant(
        tenant_id="ci-test-tenant",
        name="CI Test Tenant",
        subdomain="ci-test",
        ...
    )
    session.add(tenant)

    principal = Principal(
        tenant_id=tenant.tenant_id,
        principal_id="ci-test-principal",
        access_token="ci-test-token",  # FIXED TOKEN
        ...
    )
    session.add(principal)

    return tenant

def create_default_tenant(session) -> Tenant:
    """Create default tenant for production/local dev."""
    admin_token = secrets.token_urlsafe(32)

    tenant = Tenant(
        tenant_id="default",
        name="Default Publisher",
        subdomain="default",
        admin_token=admin_token,
        ...
    )
    session.add(tenant)

    # Create sample principals if CREATE_SAMPLE_DATA=true
    if os.environ.get("CREATE_SAMPLE_DATA") == "true":
        create_sample_principals(session, tenant.tenant_id)

    return tenant
```

**Usage**:
```bash
# Docker entrypoint (production)
python -c "from src.core.database.database import init_db; init_db(mode='default')"

# E2E test fixture
python -c "from src.core.database.database import init_db; init_db(mode='ci')"

# CI pipeline (just migrations)
python -c "from src.core.database.database import init_db; init_db(mode='skip')"
```

**Benefits**:
- Single source of truth
- Mode makes intent explicit
- Idempotent (checks for existing tenants)
- No duplicate tenant errors

### Recommendation 4: Test Isolation via Database Sessions

**Goal**: Each test gets a clean database state.

**Current Problem**:
- Tests share the same database
- One test's data affects another test
- Hard to run tests in parallel

**Proposed Solution**: Transaction-based isolation

```python
@pytest.fixture(scope="function")
def isolated_db_session(docker_services_e2e):
    """Provide isolated database session with automatic rollback."""
    from src.core.database.database_session import get_db_session

    # Get a session
    with get_db_session() as session:
        # Start a savepoint
        session.begin_nested()

        yield session

        # Rollback everything (even if test passed)
        session.rollback()
```

**Usage in Tests**:
```python
async def test_create_media_buy(isolated_db_session, live_server, test_auth_token):
    """Test media buy creation with isolated database."""
    # Any database changes in this test will be rolled back
    async with mcp_client(live_server, test_auth_token) as client:
        result = await client.call_tool("create_media_buy", {...})
        assert result["media_buy_id"]

    # On exit, database rolled back to clean state
```

**Benefits**:
- Tests don't interfere with each other
- Can run tests in parallel
- No need to clean up test data manually
- Faster (no database rebuilds between tests)

### Recommendation 5: Pre-Push Integration Test Hook

**Goal**: Catch integration failures before pushing to CI.

**Current Problem**:
- Pre-commit hooks only check static properties
- Integration failures only caught in CI
- Slow feedback loop (wait 5-10 minutes for CI)

**Proposed Solution**: Add pre-push hook that runs reference E2E test

```bash
#!/bin/bash
# .git/hooks/pre-push

echo "Running E2E integration check..."

# Only run the reference test (fast, covers main paths)
if ! pytest tests/e2e/test_adcp_reference_implementation.py -v --tb=short; then
    echo "❌ E2E reference test failed"
    echo "Run 'pytest tests/e2e/test_adcp_reference_implementation.py -v' to debug"
    exit 1
fi

echo "✅ E2E integration check passed"
```

**Benefits**:
- Catch Docker, database, schema issues locally
- Fast feedback (2-3 minutes vs 5-10 minutes)
- Prevents broken commits from reaching CI
- Can skip with `git push --no-verify` if needed

### Recommendation 6: Better Error Messages in Fixtures

**Goal**: When tests fail, make it obvious what broke.

**Current Problem**:
```
ERROR at setup of test_complete_campaign_lifecycle
subprocess.CalledProcessError: Command '['docker-compose', 'up', '-d', '--build']' returned non-zero exit status 1.
```

**What Developer Needs to Know**:
- Which service failed to start?
- What was the error message?
- Is Docker running?
- Are ports already in use?

**Proposed Solution**:
```python
def wait_for_services(mcp_port, a2a_port, max_wait=120):
    """Wait for services with detailed error reporting."""
    start_time = time.time()
    errors = []

    while time.time() - start_time < max_wait:
        # Check MCP server
        try:
            response = requests.get(f"http://localhost:{mcp_port}/health", timeout=2)
            if response.status_code == 200:
                mcp_ready = True
        except requests.ConnectionError as e:
            errors.append(f"MCP (port {mcp_port}): {e}")
        except requests.Timeout:
            errors.append(f"MCP (port {mcp_port}): Timeout")

        # Check A2A server
        try:
            response = requests.get(f"http://localhost:{a2a_port}/", timeout=2)
            if response.status_code in [200, 404, 405]:
                a2a_ready = True
        except requests.ConnectionError as e:
            errors.append(f"A2A (port {a2a_port}): {e}")
        except requests.Timeout:
            errors.append(f"A2A (port {a2a_port}): Timeout")

        if mcp_ready and a2a_ready:
            return True

        time.sleep(2)

    # Timeout - provide detailed error report
    print("\n" + "=" * 60)
    print("❌ SERVICES FAILED TO START")
    print("=" * 60)
    print(f"Waited {max_wait}s for services to become healthy")
    print("\nLast known errors:")
    for error in errors[-10:]:  # Last 10 errors
        print(f"  • {error}")

    print("\nContainer status:")
    result = subprocess.run(["docker-compose", "ps"], capture_output=True, text=True)
    print(result.stdout)

    print("\nContainer logs (last 50 lines):")
    for service in ["adcp-server", "a2a-server", "postgres"]:
        print(f"\n--- {service} ---")
        result = subprocess.run(
            ["docker-compose", "logs", "--tail=50", service],
            capture_output=True, text=True, timeout=5
        )
        print(result.stdout)

    return False
```

**Benefits**:
- Clear indication of what failed
- Container logs included automatically
- Actionable error messages
- Easier to debug both locally and in CI

---

## Action Plan

### Phase 1: Stabilize Current Tests (1-2 days)

**Priority 1: Fix Database Initialization**
1. ✅ Consolidate to single `init_db(mode="ci"|"default")` function
2. ✅ Make CI test tenant creation idempotent
3. ✅ Update `entrypoint.sh` to use `mode="default"`
4. ✅ Update E2E fixtures to use `mode="ci"`
5. ✅ Test that repeated calls don't create duplicates

**Priority 2: Fix Docker Fixture**
1. ✅ Add proper cleanup in fixture teardown
2. ✅ Add timeout protection for `docker-compose up`
3. ✅ Improve health check error messages
4. ✅ Add container log capture on failure

**Priority 3: Verify Reference Test**
1. ✅ Run `test_adcp_reference_implementation.py` locally
2. ✅ Verify it passes in CI
3. ✅ Add detailed comments explaining each phase
4. ✅ Document any assumptions (ports, tokens, etc.)

### Phase 2: Consolidate Tests (2-3 days)

**Step 1: Audit Existing Tests**
1. Review each test file for useful patterns
2. Identify which tests add unique value
3. Mark tests for deletion vs refactoring

**Step 2: Create Error Handling Test**
1. Use reference test as template
2. Add test cases for:
   - Invalid auth token
   - Missing required fields
   - Non-existent resources
   - Budget constraint violations
3. Document expected error responses

**Step 3: Refactor A2A Test**
1. Update `test_a2a_adcp_compliance.py` to use:
   - `docker_services_e2e` fixture
   - `adcp_request_builder` helpers
   - AdCP V2.3 format
2. Simplify to 3-4 core test cases
3. Remove complex validation framework (covered by unit tests)

**Step 4: Delete Obsolete Tests**
1. Delete placeholder test files (4 files)
2. Delete strategy simulation test (deprecated feature)
3. Move utilities to `tests/e2e/utils/`

### Phase 3: Improve Developer Experience (1-2 days)

**Step 1: Add Pre-Push Hook**
1. Create `.git/hooks/pre-push` script
2. Run reference E2E test before allowing push
3. Document how to skip if needed

**Step 2: Improve Documentation**
1. Update `docs/testing/e2e-testing.md` with:
   - Prerequisites (Docker, PostgreSQL, etc.)
   - How to run tests locally
   - Common error messages and solutions
   - Fixture architecture diagram
2. Add troubleshooting section to `README.md`

**Step 3: Add Monitoring**
1. Add timing metrics to E2E tests
2. Track test duration trends
3. Alert if tests become too slow

### Phase 4: Continuous Improvement (Ongoing)

**Step 1: Enforce Patterns**
1. Add pre-commit hook to check:
   - E2E tests use approved fixtures
   - E2E tests use `adcp_request_builder` helpers
   - No hardcoded ports or tokens
   - Proper error assertions

**Step 2: Regular Audits**
1. Review E2E test failures monthly
2. Identify patterns in failures
3. Update fixtures/helpers to prevent recurrence

**Step 3: CI Performance**
1. Cache Docker images in CI
2. Run E2E tests in parallel (if possible)
3. Fail fast on setup errors

---

## Success Metrics

**Before** (Current State):
- ❌ 9 E2E test files, 4 are empty placeholders
- ❌ Multiple repeated failures from same causes
- ❌ 27 tests deleted due to incompatibility
- ❌ Tests fail with unclear error messages
- ❌ No single source of truth for patterns

**After** (Target State):
- ✅ 3 high-quality E2E tests covering all paths
- ✅ Zero duplicate tenant errors
- ✅ Clear error messages with actionable guidance
- ✅ Reference implementation documented and stable
- ✅ Pre-push hook catches integration issues early
- ✅ CI failure rate < 5% (excluding infrastructure issues)

**Measurable Goals**:
- E2E test suite runs in < 5 minutes
- 95% of E2E failures are real bugs (not infra issues)
- Zero "works locally, fails in CI" incidents
- All E2E tests pass on main branch for 2+ weeks

---

## Appendix: File-by-File Recommendations

### Keep & Maintain

**`test_adcp_reference_implementation.py`** ✅
- **Status**: GOOD - Reference implementation
- **Action**: Add more comments, ensure CI stable
- **Value**: Demonstrates correct E2E pattern

**`adcp_request_builder.py`** ✅
- **Status**: GOOD - Schema-compliant helpers
- **Action**: Move to `tests/e2e/utils/`
- **Value**: Enforces AdCP V2.3 format

**`adcp_schema_validator.py`** ✅
- **Status**: GOOD - Validation utilities
- **Action**: Move to `tests/e2e/utils/`
- **Value**: Reusable validation logic

### Refactor

**`test_a2a_adcp_compliance.py`** ⚠️
- **Status**: Complex, may use old patterns
- **Action**: Simplify to 3-4 core test cases
- **Value**: Validates A2A protocol compliance

**`conftest.py`** ⚠️
- **Status**: Complex fixture management
- **Action**: Implement Recommendation 2 (Docker fixture)
- **Value**: Manages E2E test infrastructure

### Delete

**`test_strategy_simulation_end_to_end.py`** ❌
- **Reason**: Uses deprecated strategy system
- **Action**: Delete file

**`test_adcp_schema_compliance.py`** ❌
- **Reason**: Redundant (covered by contract tests + happy path)
- **Action**: Delete file

**`test_schema_validation_standalone.py`** ❌
- **Reason**: Utility script, not a test
- **Action**: Move to `scripts/validation/` if useful

**`test_adcp_full_lifecycle.py`** ❌
- **Reason**: Empty placeholder
- **Action**: Delete file

**`test_creative_lifecycle_end_to_end.py`** ❌
- **Reason**: Empty placeholder
- **Action**: Delete file

**`test_mock_server_testing_backend.py`** ❌
- **Reason**: Empty placeholder
- **Action**: Delete file

**`test_testing_hooks.py`** ❌
- **Reason**: Empty placeholder
- **Action**: Delete file

---

## Conclusion

The E2E test failures are not due to implementation bugs, but **architectural fragmentation**. Tests were written at different times using different patterns, and there was no enforcement mechanism.

**The solution is consolidation, not debugging**:
1. Keep the reference implementation as the canonical pattern
2. Refactor or delete all other tests
3. Improve fixture infrastructure (database init, Docker lifecycle)
4. Add pre-push hook to catch integration failures early
5. Document patterns clearly so future tests follow the same approach

**Estimated effort**: 4-7 days to complete all phases.

**Risk**: Low - We're consolidating to known-good patterns, not implementing new features.

**Next steps**: Review this analysis, prioritize recommendations, and begin Phase 1.
