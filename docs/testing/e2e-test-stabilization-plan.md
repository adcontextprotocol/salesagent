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

### 3. ⏳ E2E Server Startup Issues (INFRASTRUCTURE)

**Issue**: 25 E2E tests failing with connection errors: "Client failed to connect: All connection attempts failed"

**Details**:
- Server startup in GitHub Actions is unreliable
- Current wait loop: 30 attempts × 2 seconds = 60 seconds max
- Health checks: `http://localhost:8080/health` (MCP) and `http://localhost:8091/.well-known/agent.json` (A2A)

**Possible causes**:
1. Servers not starting fast enough
2. Port conflicts in CI environment
3. Database initialization taking too long
4. Process backgrounding issues (`&` in bash)

**Proposed fixes**:
1. Add retry logic with exponential backoff
2. Increase health check timeout
3. Add better logging to see what's failing
4. Consider using Docker Compose instead of manual process management
5. Add readiness probes before running tests

**Priority**: High - blocks 25+ tests from running.

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
