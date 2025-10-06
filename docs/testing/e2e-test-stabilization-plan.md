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

### 3. 🚨 E2E Servers Not Started in CI (CRITICAL INFRASTRUCTURE BUG)

**Issue**: 25 E2E tests failing with connection errors: "Client failed to connect: All connection attempts failed"

**Root Cause**: The GitHub Actions workflow uses `--skip-docker` flag but **never starts the MCP and A2A servers**!

**Evidence**:
- Workflow has "Stop background servers" step referencing `$MCP_PID` and `$A2A_PID`
- But there's NO "Start background servers" step to set these variables
- Tests try to connect to:
  - **MCP Server**: `http://localhost:8080/mcp/` (FastMCP HTTP endpoint)
  - **A2A Server**: `http://localhost:8091/.well-known/agent.json` (A2A agent endpoint)
- Both servers are not running, so all connection attempts fail

**Current workflow (BROKEN)**:
```yaml
- name: Run E2E tests
  run: |
    export PATH="$HOME/.cargo/bin:$PATH"
    uv run pytest tests/e2e/ -v --tb=short --skip-docker  # ← Expects servers running!
  continue-on-error: true

- name: Stop background servers  # ← References $MCP_PID and $A2A_PID that don't exist!
  if: always()
  run: |
    if [ ! -z "$MCP_PID" ]; then
      kill $MCP_PID 2>/dev/null || true
    fi
```

**Proposed fix**:
```yaml
- name: Start background servers
  run: |
    # Start MCP server in background
    uv run python -m src.core.main &
    export MCP_PID=$!
    echo "MCP_PID=$MCP_PID" >> $GITHUB_ENV

    # Start A2A server in background
    uv run python -m src.a2a_server.server &
    export A2A_PID=$!
    echo "A2A_PID=$A2A_PID" >> $GITHUB_ENV

    # Wait for health checks
    for i in {1..30}; do
      if curl -sf http://localhost:8080/health > /dev/null && \
         curl -sf http://localhost:8091/.well-known/agent.json > /dev/null; then
        echo "✓ Both servers ready"
        break
      fi
      sleep 2
    done

- name: Run E2E tests
  run: |
    export PATH="$HOME/.cargo/bin:$PATH"
    uv run pytest tests/e2e/ -v --tb=short --skip-docker
  continue-on-error: true

- name: Stop background servers
  if: always()
  run: |
    kill $MCP_PID $A2A_PID 2>/dev/null || true
```

**Alternative**: Remove `--skip-docker` and let pytest manage Docker Compose (more reliable).

**Priority**: 🔥 CRITICAL - This is why all E2E connection tests fail!

### 4. 🐛 Schema Validation Test Failures (DATA)

**Issue**: 29 tests failing with "Schema validation failed for get-products response"

**Root cause**: The actual Product data returned by `get_products` doesn't include `property_tags` or `properties`.

**Fix dependencies**: Requires fix #2 (add property_tags to Product model).

**Priority**: High - related to architectural issue above.

## Stabilization Roadmap

### Phase 1: Quick Wins (Current)
- [x] Add `adcp_version` to GetProductsResponse
- [x] Fix test data in test_schema_validation_standalone.py
- [x] Document issues

### Phase 2: Server Reliability
- [ ] Improve server startup in CI
  - Add better health check retry logic
  - Increase timeouts
  - Add detailed logging
- [ ] Consider Docker Compose for E2E tests
- [ ] Add startup failure diagnostics

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
