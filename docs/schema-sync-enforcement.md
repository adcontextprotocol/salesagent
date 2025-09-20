# AdCP Schema Sync Enforcement

## Overview

This system ensures our AdCP implementation stays in sync with the latest schema specifications by enforcing schema compliance at both pre-commit and CI levels.

## Why This Matters

During rapid AdCP protocol evolution, schema drift can cause:
- ❌ **Buyer agent integration failures** (like the `formats` vs `format_ids` issue)
- ❌ **Production compatibility issues** with external clients
- ❌ **Regression in protocol compliance**
- ❌ **Silent breaking changes** that tests don't catch

## Enforcement Points

### 🚧 Pre-Commit Hook (Local Development)
- **Hook ID**: `adcp-schema-sync`
- **Command**: `uv run python scripts/check_schema_sync.py --ci`
- **Behavior**: Blocks commits if schema issues are detected
- **Override**: Use `git commit --no-verify` (NOT recommended)

### 🤖 CI Pipeline (GitHub Actions)
- **Job**: `schema-sync` (runs before all other tests)
- **Command**: `uv run python scripts/check_schema_sync.py --ci`
- **Behavior**: Fails CI if schema issues are detected
- **Dependency**: All other CI jobs depend on this passing

## What Gets Checked

### ✅ Schema Compliance Checks

1. **Product Response Format**
   - Field naming: `format_ids` (not `formats`)
   - Required fields presence
   - Null field exclusion (`measurement`, `creative_policy`)
   - Internal field exclusion (`expires_at`, `implementation_config`)

2. **GetProducts Response Structure**
   - Correct response wrapper
   - Product array compliance
   - Each product follows schema

3. **Schema File Freshness**
   - Cached schemas not older than 1 week
   - Key schema files present

4. **Cached Schema Consistency**
   - Internal consistency checks
   - Field naming alignment with buyer expectations

### ❌ Current Known Issue (Expected)

```
❌ ERROR: Cached schema uses 'formats' but buyers expect 'format_ids'
```

This is **expected during transition period**:
- ✅ Our implementation correctly returns `format_ids`
- ❌ Cached schemas still use `formats`
- 🎯 We're aligned with buyer expectations, not outdated cached schemas

## How to Resolve Schema Issues

### Option 1: Update Schemas (Preferred)
```bash
# Update to latest AdCP schemas
uv run python scripts/check_schema_sync.py --update

# Verify fix
uv run python scripts/check_schema_sync.py
```

### Option 2: Review and Accept Current State
```bash
# Check what specifically failed
uv run python scripts/check_schema_sync.py --ci

# If our implementation is correct but schemas are outdated,
# the issue may resolve when AdCP publishes updated schemas
```

### Option 3: Emergency Override (Use Sparingly)
```bash
# Pre-commit override (local only)
git commit --no-verify -m "emergency fix: schema check override"

# Note: CI will still fail - this only bypasses local pre-commit
```

## Schema Sync Workflow

### 🔄 Normal Development Flow

1. **Make code changes**
2. **Run tests locally**: `uv run pytest`
3. **Commit**: `git commit -m "your changes"`
4. **Pre-commit hook runs**: Checks schema sync
5. **If pass**: Commit proceeds
6. **If fail**: Fix schema issues before committing
7. **Push**: `git push`
8. **CI runs**: Schema sync check runs first
9. **If pass**: Other CI jobs proceed
10. **If fail**: PR blocked until schema issues resolved

### 🚨 Schema Drift Detected

1. **Pre-commit/CI fails** with schema sync errors
2. **Investigate**: Run `uv run python scripts/check_schema_sync.py`
3. **Two scenarios**:

   **A. Our implementation is wrong:**
   - Fix our schema models
   - Update `src/core/schemas.py`
   - Ensure AdCP compliance

   **B. Cached schemas are outdated:**
   - Update schemas: `scripts/check_schema_sync.py --update`
   - Verify alignment with buyer expectations
   - Commit updated schemas

4. **Re-run check**: `uv run python scripts/check_schema_sync.py`
5. **Commit**: Should now pass both local and CI checks

## Monitoring & Maintenance

### Weekly Schema Health Check
```bash
# Check for schema drift
uv run python scripts/check_schema_sync.py

# Update if needed
uv run python scripts/check_schema_sync.py --update
```

### Schema Update Automation (Future)
- **Goal**: Automated PRs when schemas change
- **Trigger**: Weekly cron job or webhook from AdCP registry
- **Action**: Update schemas, run tests, create PR if changes detected

## Configuration

### Current Settings (in `scripts/check_schema_sync.py`)
```python
expected_requirements = {
    "product_format_field": "format_ids",  # Not "formats"
    "max_schema_age_hours": 168,  # 1 week
    "excluded_null_fields": ["measurement", "creative_policy"],
    "excluded_internal_fields": ["expires_at", "implementation_config"],
}
```

### Adjusting Strictness
- **More strict**: Reduce `max_schema_age_hours`
- **Less strict**: Increase tolerance or move checks to warnings
- **Different fields**: Update field expectations based on buyer feedback

## Troubleshooting

### Pre-commit Hook Not Running
```bash
# Install/update pre-commit hooks
pre-commit install
pre-commit autoupdate
```

### CI Job Failing Unexpectedly
```bash
# Check specific error in GitHub Actions logs
# Look for "AdCP Schema Sync Check" job
# Review error details and run locally:
uv run python scripts/check_schema_sync.py --ci
```

### Schema Update Script Failing
```bash
# If schema download fails, check:
# 1. Network connectivity
# 2. AdCP registry URL changes
# 3. Authentication requirements

# Fallback: Use cached schemas and investigate endpoint changes
```

### False Positives
```bash
# If check incorrectly fails:
# 1. Review check logic in scripts/check_schema_sync.py
# 2. Update expectations if AdCP spec changed
# 3. Temporarily adjust strictness if needed
```

## Benefits

### 🎯 Early Detection
- Catch schema drift before it reaches production
- Prevent buyer agent integration failures
- Block commits with protocol violations

### 🤖 Automated Enforcement
- No manual schema checking required
- Consistent enforcement across all developers
- CI-level protection for main branch

### 📊 Visibility
- Clear error messages with fix instructions
- Distinguishes between implementation issues vs cached schema issues
- Tracks schema compliance over time

### 🚀 Rapid Iteration Support
- Supports fast-moving AdCP protocol development
- Ensures compatibility during spec evolution
- Reduces debugging time for integration issues

## Examples

### ✅ Successful Schema Sync Check
```
🔍 Running AdCP Schema Sync Checks...

📋 Checking: Product Response Format
✅ Product response format compliant

📋 Checking: GetProducts Response Format
✅ GetProductsResponse format compliant

📋 Checking: Schema File Freshness
✅ Schema files are fresh

📋 Checking: Cached Schema Consistency
✅ Cached schema uses expected 'format_ids' field

📊 Schema Sync Check Summary:
   ✅ Checks passed: 4
   ❌ Errors: 0
   ⚠️ Warnings: 0

🎉 All schema sync checks passed!
```

### ❌ Schema Sync Check Failure
```
📊 Schema Sync Check Summary:
   ✅ Checks passed: 3
   ❌ Errors: 1
   ⚠️ Warnings: 0

❌ ERRORS:
   • Product response missing 'format_ids' field

💥 Schema sync check failed!

To fix schema issues, run:
   uv run python scripts/check_schema_sync.py --update
   uv run python scripts/check_schema_sync.py
```

---

## Summary

This schema sync enforcement system ensures we stay current with AdCP specifications and maintain buyer agent compatibility. It catches schema drift early, provides clear fix instructions, and supports the rapid evolution of the AdCP protocol.

**Key principle**: Treat schema compliance as a hard requirement, not optional - buyer agents depend on our adherence to the spec.
