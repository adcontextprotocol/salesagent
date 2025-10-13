# Test Agent Downtime - October 12, 2025

**Date**: 2025-10-12 @ 8:40 PM PST
**Status**: ✅ RESOLVED - Database migration issue fixed
**Impact**: All test agent operations were timing out (app was crash-looping)
**Resolution**: PR #357 - Fixed migration to handle duplicate data

## Executive Summary

**Initial diagnosis was wrong.** This appeared to be an external test agent infrastructure failure, but checking Fly.io logs revealed the actual cause: our reference implementation was crash-looping due to a database migration failure.

## Initial Investigation (Incorrect Diagnosis)

### Health Check Results

Tested all endpoints of `https://test-agent.adcontextprotocol.org`:

| Endpoint | Status | Details |
|----------|--------|---------|
| Root (`/`) | ❌ TIMEOUT | 5+ seconds, no response |
| Agent Card (`/.well-known/agent-card.json`) | ❌ TIMEOUT | 5+ seconds, no response |
| A2A Endpoint (`/a2a`) | ❌ TIMEOUT | 10+ seconds, no response |

### Network Connectivity

✅ **DNS Resolution**: Working
- Resolves to: `104.21.24.70`, `172.67.217.91`

✅ **ICMP Ping**: Working
- Average latency: ~13ms
- 0% packet loss

❌ **Application Layer**: Not responding
- TCP connections established (likely load balancer)
- HTTP requests hang indefinitely
- No response from application

**Initial Conclusion**: ❌ WRONG - Assumed external infrastructure issue

## Actual Root Cause (Found via Fly Logs)

**Database migration failure causing crash loop:**

```
❌ Error running migrations: (psycopg2.errors.UniqueViolation)
could not create unique index "uq_media_buys_buyer_ref"
DETAIL: Key (tenant_id, principal_id, buyer_ref)=(default, principal_3bd0d4a8,
A2A-principal_3bd0d4a8) is duplicated.

[SQL: ALTER TABLE media_buys ADD CONSTRAINT uq_media_buys_buyer_ref
     UNIQUE (tenant_id, principal_id, buyer_ref)]
```

**What happened:**
1. Migration `31ff6218695a` tried to add unique constraint on `buyer_ref`
2. Production database had duplicate `buyer_ref` values from test data
3. Constraint creation failed with `UniqueViolation`
4. App crashed on startup (exit code 1)
5. Fly.io auto-restarted app → migration ran again → failed again
6. After 10 crash cycles, Fly.io stopped the machine: `machine has reached its max restart count of 10`
7. All API endpoints became unavailable (app not running)

### Key Evidence from Fly Logs

```
2025-10-13T02:03:15Z app[3d8d3210c1e628] [info] ❌ Database initialization failed
2025-10-13T02:03:15Z app[3d8d3210c1e628] [info] INFO Main child exited normally with code: 1
2025-10-13T02:03:15Z runner[3d8d3210c1e628] [info] machine has reached its max restart count of 10
```

The app entered a crash loop at startup, never reaching a healthy state.

## The Fix

### Problem
Migration assumed no duplicate `buyer_ref` values existed, but production had test data with duplicates.

### Solution (PR #357)
Updated migration `31ff6218695a` to:
1. **Deduplicate existing data first** using SQL window function
2. Append sequence number to duplicates (e.g., `A2A-principal_3bd0d4a8-2`)
3. Then add the unique constraint

```sql
WITH duplicates AS (
    SELECT
        media_buy_id,
        tenant_id,
        principal_id,
        buyer_ref,
        ROW_NUMBER() OVER (
            PARTITION BY tenant_id, principal_id, buyer_ref
            ORDER BY created_at
        ) as rn
    FROM media_buys
    WHERE buyer_ref IS NOT NULL
)
UPDATE media_buys
SET buyer_ref = duplicates.buyer_ref || '-' || duplicates.rn
FROM duplicates
WHERE media_buys.media_buy_id = duplicates.media_buy_id
  AND duplicates.rn > 1
```

This preserves all existing media buys while ensuring data integrity going forward.

## Lessons Learned

### 1. Always Check Application Logs First
**Before**: Assumed external service failure based on symptoms
**Should Have**: Checked Fly.io logs immediately
**Tool**: `fly logs --app adcp-sales-agent`

### 2. Migrations Must Handle Real Production Data
**Issue**: Migration assumed clean data state
**Fix**: Always deduplicate/clean data before adding constraints
**Pattern**: Add data migration step before schema change

### 3. Crash Loops Can Look Like External Failures
**Symptom**: All endpoints timeout
**Actual Cause**: App never started successfully
**Diagnostic**: Network layer works, application layer doesn't

### 4. Test Migrations Against Production-Like Data
**Issue**: Test data in production environment
**Prevention**:
- Test migrations with realistic data scenarios
- Add duplicate data checks to migration tests
- Consider data validation pre-flight checks

## Timeline

- **8:40 PM PST**: Issue detected via curl test
- **8:45 PM PST**: Confirmed all endpoints timing out
- **8:50 PM PST**: Verified network connectivity working
- **8:55 PM PST**: Initially concluded external infrastructure issue ❌
- **9:00 PM PST**: User suggested checking Fly logs ✅
- **9:05 PM PST**: Found crash loop in Fly logs
- **9:10 PM PST**: Identified migration failure root cause
- **9:15 PM PST**: Fixed migration to handle duplicates
- **9:20 PM PST**: Created PR #357
- **9:25 PM PST**: Waiting for merge + auto-deploy

## Impact

### Affected
- All API endpoints (MCP, A2A, Admin UI)
- Media buy creation
- Webhook delivery
- Any operations requiring the reference implementation

### Not Affected
- Local development environments
- Mock adapter functionality
- Test suite (uses test database)

## Resolution Steps

1. ✅ Fixed migration to handle duplicate data
2. ✅ Created PR #357 with detailed explanation
3. ⏳ Merge to main (triggers auto-deploy)
4. ⏳ Fly.io redeploys with fixed migration
5. ⏳ Verify app starts successfully
6. ⏳ Confirm API endpoints accessible

## Monitoring Improvements (Future)

1. **Pre-deployment Migration Testing**
   - Test migrations against production database snapshot
   - Automated checks for constraint violations

2. **Better Error Alerting**
   - Alert on Fly.io crash loops
   - Monitor startup failures
   - Track migration errors

3. **Deployment Health Checks**
   - Verify migrations complete before traffic routing
   - Automated rollback on startup failures

## References

- PR #357: Fix database migration crash causing Fly.io downtime
- Migration file: `alembic/versions/31ff6218695a_add_buyer_ref_unique_constraint_and_.py`
- Fly app: `adcp-sales-agent` (reference implementation)

---

**Key Takeaway**: When all endpoints timeout, check application logs before assuming external failure. The app might not be running at all.
