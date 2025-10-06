# E2E Test Stabilization Plan

## Current Status

As of 2025-10-06, E2E tests are running with `continue-on-error: true` because they are not yet stable enough to block CI. This document tracks the issues that need to be resolved before making E2E tests blocking.

## Issues Identified

### 1. ✅ Missing `adcp_version` Field (FIXED)

**Issue**: `GetProductsResponse` was missing the required `adcp_version` field per AdCP spec.

**Fix**: Added `adcp_version: str = Field(default="1.0.0", ...)` to `GetProductsResponse` schema (commit 8ac94f2).

**Impact**: Schema validation tests now pass for `get-products` responses.

### 2. ⚠️ Product Model Missing `properties`/`property_tags` (ARCHITECTURAL)

**Issue**: The `Product` model doesn't include `properties` or `property_tags` fields, which are required by the AdCP spec (oneOf constraint).

**Details**:
- AdCP spec requires products to have EITHER:
  - `properties`: array of Property objects, OR
  - `property_tags`: array of string tags

**Current workaround**: Test data manually adds `property_tags` to validate schema structure.

**Proposed fix**:
1. Add `property_tags: list[str] | None = None` to Product model
2. Populate from tenant/product configuration
3. Alternatively, add `properties: list[Property] | None = None` if we want full property data

**Priority**: Medium - doesn't block basic functionality, but needed for full AdCP compliance.

### 3. ✅ E2E Servers Not Started in CI (FIXED)

**Issue**: 25 E2E tests failing with connection errors: "Client failed to connect: All connection attempts failed"

**Root Cause**: The GitHub Actions workflow was managing servers manually with background processes, but the process management was unreliable:
- Complex shell scripts to start MCP and A2A servers in background
- Manual health check loops that could fail or timeout
- `$GITHUB_ENV` variable passing between steps was fragile

**Solution**: Let pytest manage Docker Compose automatically via `conftest.py`

**Previous workflow (COMPLEX)**:
```yaml
- name: Start AdCP server in background  # ← Manual process management
  run: |
    uv run python scripts/run_server.py &
    MCP_PID=$!
    # 30+ lines of startup scripts and health checks...

- name: Run E2E tests
  run: uv run pytest tests/e2e/ -v --tb=short --skip-docker

- name: Stop background servers
  run: kill $MCP_PID $A2A_PID
```

**New workflow (SIMPLE)**:
```yaml
- name: Install Docker Compose
  run: sudo apt-get install -y docker-compose

- name: Run E2E tests
  run: uv run pytest tests/e2e/ -v --tb=short  # ← No --skip-docker!

- name: Cleanup Docker services
  run: docker-compose down -v
```

**Benefits**:
- Pytest's `conftest.py` handles Docker Compose lifecycle automatically
- Built-in health checks and retry logic (60 second timeout)
- Reliable server startup with proper isolation
- Simpler CI configuration (fewer moving parts)

**Status**: ✅ FIXED - Committed in this PR

**Priority**: Was 🔥 CRITICAL - Now resolved!

### 4. 🐛 Schema Validation Test Failures (DATA)

**Issue**: 29 tests failing with "Schema validation failed for get-products response"

**Root cause**: The actual Product data returned by `get_products` doesn't include `property_tags` or `properties`.

**Fix dependencies**: Requires fix #2 (add property_tags to Product model).

**Priority**: High - related to architectural issue above.

## Stabilization Roadmap

### Phase 1: Quick Wins ✅ COMPLETE
- [x] Add `adcp_version` to GetProductsResponse
- [x] Fix test data in test_schema_validation_standalone.py
- [x] Document issues

### Phase 2: Server Reliability ✅ COMPLETE
- [x] Switch to Docker Compose for E2E tests
- [x] Remove manual server management from CI
- [x] Simplify workflow configuration
- [x] Let pytest handle health checks and startup

### Phase 3: Schema Compliance
- [ ] Add `property_tags` field to Product model
- [ ] Populate property_tags from configuration
- [ ] Update Product serialization
- [ ] Verify all E2E tests pass locally

### Phase 4: Stabilization
- [ ] Run E2E tests on multiple PRs
- [ ] Monitor for flakiness
- [ ] Fix any intermittent failures
- [ ] Document test environment requirements

### Phase 5: Make Blocking
- [ ] Remove `continue-on-error: true` from E2E test step
- [ ] Add E2E tests to test-summary dependencies
- [ ] Update documentation

## Test Execution Timeline

**Target**: 2 weeks of stable E2E runs before making blocking

**Criteria for "stable"**:
- 95%+ pass rate across multiple PRs
- No intermittent failures
- All schema validation passes
- Connection issues resolved

## Related Issues

- #283 - Improve A2A test coverage (current PR)
- #282 - Fix create_media_buy A2A serialization bug

## References

- AdCP Specification: https://adcontextprotocol.org/
- AdCP Schema v1: https://adcontextprotocol.org/schemas/v1/
- Product Schema: https://adcontextprotocol.org/schemas/v1/core/product.json
