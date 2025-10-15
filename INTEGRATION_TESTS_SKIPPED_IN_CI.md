# 🚨 CRITICAL: Integration Tests Are Skipped in CI

## The Problem

**Integration tests are being SKIPPED in GitHub Actions CI**, meaning bugs like the missing `await` in A2A create_media_buy are not caught before deployment.

## Root Cause

**Environment Variable Mismatch:**

| Environment | Variable Set | Tests Run? |
|-------------|-------------|------------|
| Local `run_all_tests.sh ci` | `ADCP_TEST_DB_URL` | ✅ YES |
| GitHub Actions CI | `DATABASE_URL` only | ❌ NO - SKIPPED |

**Code Reference:**
```python
# tests/integration/conftest.py:38-40
postgres_url = os.environ.get("ADCP_TEST_DB_URL")
if not postgres_url:
    pytest.skip("Integration tests require PostgreSQL. Run: ./run_all_tests.sh ci")
```

## Evidence

1. **Test was skipped locally:**
   ```
   SKIPPED [1] tests/integration/test_a2a_skill_invocation.py:338:
   Integration tests require PostgreSQL. Run: ./run_all_tests.sh ci
   ```

2. **CI only sets `DATABASE_URL`:**
   ```yaml
   # .github/workflows/test.yml
   - name: Run integration tests
     env:
       DATABASE_URL: postgresql://adcp_user:test_password@localhost:5432/adcp_test
       # ❌ MISSING: ADCP_TEST_DB_URL
   ```

3. **Local script sets both:**
   ```bash
   # run_all_tests.sh
   export ADCP_TEST_DB_URL="postgresql://adcp_user:test_password@localhost:5433/adcp_test"
   export DATABASE_URL="$ADCP_TEST_DB_URL"  # ✅ Sets both
   ```

## Impact

**ALL integration tests are being skipped in CI**, including:
- ✅ 46+ integration test files in `tests/integration/`
- ✅ A2A endpoint tests
- ✅ MCP tool tests
- ✅ Database persistence tests
- ✅ Admin UI tests
- ✅ Adapter tests

**This means:**
- Bugs reach production (like the missing `await`)
- Database issues aren't caught
- Integration failures slip through
- False sense of security from "passing" CI

## The Fix

### Option 1: Add ADCP_TEST_DB_URL to CI (Quick Fix)

```yaml
# .github/workflows/test.yml
- name: Run integration tests
  env:
    DATABASE_URL: postgresql://adcp_user:test_password@localhost:5432/adcp_test
    ADCP_TEST_DB_URL: postgresql://adcp_user:test_password@localhost:5432/adcp_test
    GEMINI_API_KEY: test_key_for_mocking
    # ... rest of env vars
```

### Option 2: Update Fixture to Use DATABASE_URL (Better Long-term)

```python
# tests/integration/conftest.py:38
# Use DATABASE_URL if ADCP_TEST_DB_URL not set (backwards compatible)
postgres_url = os.environ.get("ADCP_TEST_DB_URL") or os.environ.get("DATABASE_URL")
if not postgres_url or not postgres_url.startswith("postgresql://"):
    pytest.skip("Integration tests require PostgreSQL. Run: ./run_all_tests.sh ci")
```

**Benefits:**
- Works with both local and CI setups
- Backwards compatible
- Removes duplicate configuration
- Aligns with "one database, one truth" principle

### Option 3: Both (Recommended)

1. Update fixture to fallback to `DATABASE_URL`
2. Update CI to set `ADCP_TEST_DB_URL` explicitly for clarity
3. Document that `ADCP_TEST_DB_URL` is preferred but `DATABASE_URL` works

## Verification Steps

After fixing:

1. **Check test count before:**
   ```bash
   gh run view <run-id> --log | grep "integration-tests" | grep "passed\|skipped"
   ```

2. **Apply fix**

3. **Check test count after:**
   - Should see ~46 integration tests running
   - Should see 0 skipped (except `skip_ci` marked tests)

4. **Verify specific test runs:**
   ```bash
   # Should find this in logs:
   tests/integration/test_a2a_skill_invocation.py::TestA2ASkillInvocation::test_explicit_skill_create_media_buy PASSED
   ```

## Why This Happened

**The fixtures are in the RIGHT place** (`tests/integration/`), but:
1. Local testing script evolved to use `ADCP_TEST_DB_URL` for isolation
2. CI was never updated to match
3. Tests silently skip with no failure, so it went unnoticed
4. Pre-commit hooks can't detect runtime skips

## Related Issues

This explains why:
- The missing `await` bug wasn't caught
- Integration bugs make it to production
- CI appears to pass but doesn't test integrations
- `run_all_tests.sh ci` is critical for catching real bugs

## Recommended Actions

**Immediate (Critical):**
1. ✅ Fix missing `await` bug (already done)
2. 🔴 **Update CI to set ADCP_TEST_DB_URL** (blocks future bugs)
3. 🔴 **Verify integration tests run in next CI run**

**Short-term (Important):**
4. Update fixture to fallback to DATABASE_URL
5. Add CI check that fails if integration tests are skipped
6. Document environment variable requirements

**Long-term (Nice to have):**
7. Add pre-push hook that requires `run_all_tests.sh ci`
8. Consider making test skip count a CI failure condition
9. Add monitoring for skipped test trends

## Files to Update

1. `.github/workflows/test.yml` - Add `ADCP_TEST_DB_URL` env var
2. `tests/integration/conftest.py` - Fallback to `DATABASE_URL`
3. `docs/testing/` - Document environment setup requirements
