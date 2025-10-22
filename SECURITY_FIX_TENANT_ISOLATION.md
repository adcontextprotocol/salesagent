# CRITICAL SECURITY FIX: Tenant Isolation Breach

## Summary

**SEVERITY**: CRITICAL
**DATE**: 2025-10-22
**AFFECTED**: Production multi-tenant deployment
**STATUS**: Fixed in code, production database configuration required

## The Problem

A user called the Wonderstruck **MCP endpoint** with a valid authentication token:

```bash
curl -X POST "https://wonderstruck.sales-agent.scope3.com/mcp" \
  -H "Authorization: Bearer vWaSGnlH9oPOVqTfhJ1m9orXxOPmZYozu7LKdBCLaZc" \
  ...
```

**Expected**: Get products from the Wonderstruck tenant
**Actual**: Got products from the Test Agent tenant (`prod_d979b543`, `prod_e8fd6012`)

This is a **complete tenant isolation breach** - cross-tenant data leakage.

**Why Only MCP?** The breach only occurred in MCP, not A2A, because:
- **MCP**: Extracts tenant from Host header subdomain, then validates token against that tenant
- **A2A**: Relies on global token lookup (searches all tenants for token, sets correct tenant as side effect)
- When MCP's subdomain lookup failed (wonderstruck not in DB), it fell back to global lookup
- Global lookup found a token from a different tenant (test-agent), causing the breach

## Root Cause

### 1. Dangerous Fallback Logic

In `src/core/config_loader.py`:

```python
def get_current_tenant() -> dict[str, Any]:
    tenant = current_tenant.get()
    if not tenant:
        # SECURITY BUG: Falls back to first active tenant!
        tenant = get_default_tenant()  # Returns ORDER BY created_at LIMIT 1
    return tenant
```

When no tenant context was set, the code **silently returned the first active tenant** from the database. This is catastrophic in multi-tenant environments.

### 2. Global Token Lookup

In `src/core/main.py` (line 516):

```python
if not requested_tenant_id:
    console.print("[yellow]No tenant detected - will use global token lookup[/yellow]")
    # Searches ALL tenants for the token, sets that tenant's context
    principal_id = get_principal_from_token(auth_token, tenant_id=None)
```

When tenant detection failed (subdomain not found), the code searched **all tenants globally** for the token. If it found a principal in a different tenant, it set that tenant's context, causing the breach.

## Attack Scenario

1. Attacker creates account with Tenant A
2. Attacker gets valid authentication token for Tenant A
3. Attacker sends request to Tenant B's subdomain with Tenant A's token
4. If Tenant B doesn't exist in database (subdomain lookup fails), system falls back to global token lookup
5. System finds Tenant A's token, sets Tenant A's context
6. Attacker now sees Tenant A's data through Tenant B's endpoint

## The Fix

### Code Changes (This PR)

**1. Remove Dangerous Fallback** (`src/core/config_loader.py:34-46`)

```python
def get_current_tenant() -> dict[str, Any]:
    tenant = current_tenant.get()
    if not tenant:
        # SECURITY: Do NOT fall back to default tenant.
        raise RuntimeError(
            "No tenant context set. Tenant must be set via set_current_tenant() "
            "before calling this function. This is a critical security error - "
            "falling back to default tenant would breach tenant isolation."
        )
    return tenant
```

**2. Reject Requests Without Tenant Detection** (`src/core/main.py:516-529`)

```python
if not requested_tenant_id:
    # SECURITY: If token is provided but tenant cannot be determined, reject.
    raise ToolError(
        "TENANT_DETECTION_FAILED",
        f"Cannot determine tenant from request. Please ensure the Host header "
        f"contains a valid subdomain (e.g., 'wonderstruck.sales-agent.scope3.com')"
    )
```

### Production Fix Required

**The wonderstruck tenant must exist in the database with correct subdomain.**

Check production database:

```sql
SELECT tenant_id, name, subdomain, is_active
FROM tenants
WHERE subdomain = 'wonderstruck' AND is_active = true;
```

If missing or incorrect:

```sql
-- If tenant exists but wrong subdomain:
UPDATE tenants
SET subdomain = 'wonderstruck'
WHERE tenant_id = 'tenant_wonderstruck';

-- If tenant doesn't exist:
INSERT INTO tenants (tenant_id, name, subdomain, is_active, created_at, updated_at)
VALUES ('tenant_wonderstruck', 'Wonderstruck', 'wonderstruck', true, NOW(), NOW());
```

Also verify the principal/token exists:

```sql
SELECT principal_id, tenant_id, name
FROM principals
WHERE access_token = 'vWaSGnlH9oPOVqTfhJ1m9orXxOPmZYozu7LKdBCLaZc';
```

Expected: `tenant_id = 'tenant_wonderstruck'`

## Impact

### Before Fix
- ❌ Cross-tenant data leakage possible
- ❌ Silent failures with wrong data
- ❌ Unpredictable behavior when subdomain lookup fails
- ❌ First active tenant gets all unroutable requests

### After Fix
- ✅ Tenant isolation enforced at code level
- ✅ Clear error messages when tenant can't be determined
- ✅ No silent fallbacks to wrong tenants
- ✅ Fail loudly and fast instead of returning wrong data

### Behavioral Changes

**Discovery endpoints (no auth):**
- No change - still work without authentication

**Authenticated requests:**
- **Now require** valid subdomain in Host header OR x-adcp-tenant header
- Requests without detectable tenant will get `TENANT_DETECTION_FAILED` error
- Requests with wrong tenant for token will get `INVALID_AUTH_TOKEN` error

## Testing

Run the new test suite:

```bash
uv run pytest tests/unit/test_tenant_isolation_breach_fix.py -v
```

Tests verify:
1. ✅ No fallback to default tenant
2. ✅ Tenant detection from subdomain works
3. ✅ Cross-tenant tokens are rejected
4. ✅ Clear error messages for debugging

## Deployment Plan

1. ✅ Merge this PR (code fixes)
2. ⚠️ Verify all production tenants have correct `subdomain` field
3. ⚠️ Deploy to production
4. ⚠️ Monitor logs for `TENANT_DETECTION_FAILED` errors
5. ⚠️ Fix any missing tenant configurations

## Monitoring

Watch for these errors in production:

- `TENANT_DETECTION_FAILED` → Missing or incorrect subdomain in database
- `INVALID_AUTH_TOKEN` → Token belongs to different tenant than detected

These errors indicate **legitimate security protections** preventing cross-tenant access.

## References

- Bug report: User got test-agent products when calling wonderstruck endpoint
- File: `/Users/brianokelley/Library/Application Support/com.conductor.app/uploads/originals/0c2e66fd-d9bb-4c1a-85ab-cb087b3da1f8.txt`
- Code changes: `src/core/config_loader.py`, `src/core/main.py`
- Tests: `tests/unit/test_tenant_isolation_breach_fix.py`
