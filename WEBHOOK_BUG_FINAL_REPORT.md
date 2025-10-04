# Sales Agent Webhook Bug Report - Final Status

**Date**: 2025-10-04
**Reporter**: Activation API Team
**Priority**: High
**Status**: Partially Fixed - Webhook Still Not Sending

## Executive Summary

Media buy creation now succeeds (status: "working"), and workflow mapping is correctly inserted with `action='create'`. However, **webhooks are still not being sent** despite all prerequisite conditions being met.

## Current Status

### ✅ What's Working

1. **Media Buy Creation**: Successfully creates media buy
   - Response: `status: "working"`, `media_buy_id: "buy_TEST-XXX"`
   - No longer returns `status: "failed"`

2. **Workflow Mapping**: Correctly inserts into `object_workflow_mapping`
   ```sql
   SELECT * FROM object_workflow_mapping ORDER BY created_at DESC LIMIT 1;

   id | object_type | object_id       | step_id             | action
   ---|-------------|-----------------|---------------------|--------
   2  | media_buy   | buy_TEST-9oko32 | step_dbc3107f8e1a  | create
   ```

3. **Workflow Completion**: Workflow step completes successfully
   ```sql
   SELECT step_id, status, completed_at FROM workflow_steps
   WHERE step_id = 'step_dbc3107f8e1a';

   step_id             | status    | completed_at
   --------------------|-----------|---------------------------
   step_dbc3107f8e1a   | completed | 2025-10-04 01:51:12.960585
   ```

4. **Webhook Registration**: Webhook URL correctly registered
   ```sql
   SELECT id, url, is_active, created_at FROM push_notification_configs
   ORDER BY created_at DESC LIMIT 1;

   id                  | url                                                              | is_active | created_at
   --------------------|------------------------------------------------------------------|-----------|---------------------------
   mcp_d175ca4233d64641| http://localhost:3001/webhooks/creative-status/123/creative_... | t         | 2025-10-04 01:51:12.953264
   ```

### ❌ What's NOT Working

**Webhook POST is never sent** despite all conditions being met.

## Test Case

### Input
```bash
npx tsx scripts/test-real-webhook-flow.ts
```

### Expected Behavior
1. Create media buy with webhook_url
2. Media buy created successfully ✅
3. Workflow mapping inserted ✅
4. Workflow step completes ✅
5. Push notification service triggers ❌ (This is where it fails)
6. HTTP POST sent to webhook_url ❌
7. Activation API receives webhook ❌
8. Action marked as completed ❌

### Actual Behavior
- Steps 1-4 complete successfully
- No webhook POST is ever sent
- Activation API waits 60 seconds for webhook (times out)
- Action remains in "pending" or "in_progress" status

## Database Evidence

### Test Run: 2025-10-04 01:51:12

**Media Buy Created**:
```sql
buy_TEST-9oko32  -- Successfully created
```

**Workflow Mapping** (Fixed!):
```
object_type: media_buy
object_id: buy_TEST-9oko32
step_id: step_dbc3107f8e1a
action: create  ← Previously was NULL, now correct
```

**Workflow Step**:
```
step_id: step_dbc3107f8e1a
status: completed
completed_at: 2025-10-04 01:51:12.960585  (within 1 second of creation)
```

**Push Notification Config**:
```
url: http://localhost:3001/webhooks/creative-status/123/creative_IrOrkvPk
is_active: true
created_at: 2025-10-04 01:51:12.953264
```

## What We Know

### Previous Bug (FIXED ✅)
- **Issue**: `action` column in `object_workflow_mapping` was NULL
- **Cause**: `create_media_buy` function didn't set the `action` parameter
- **Status**: ✅ FIXED - Now correctly inserts `action='create'`

### Current Bug (OPEN ❌)
- **Issue**: Webhook POST is never sent
- **Likely Cause**: Push notification service logic has additional checks that fail silently
- **Impact**: Webhooks never arrive at activation API

## Debugging Steps Performed

1. ✅ Verified workflow mapping exists
2. ✅ Verified workflow step completed
3. ✅ Verified push notification config exists
4. ✅ Confirmed webhook URL is reachable (manual curl test succeeded)
5. ✅ Checked backend logs for webhook trigger (no output found)

## Hypotheses for Current Bug

### Most Likely: Silent Failure in Push Notification Service

The push notification service may be:
1. **Not finding the notification config** despite it existing
   - Query logic may be incorrect
   - Join conditions may be too restrictive

2. **Failing authentication/validation checks**
   - URL validation failing
   - Authentication token check failing (even though token is empty)
   - Principal/tenant validation failing

3. **Checking additional conditions we're not aware of**
   - Media buy status check
   - Package status check
   - Some business rule that prevents webhook sending

### Less Likely but Possible
- Event loop issue preventing webhook task from executing
- Exception being silently swallowed
- Webhook sending code not being called at all

## What We Need from Sales Agent Team

### 1. Enhanced Debug Logging

Add comprehensive logging to push notification service:

```python
# When workflow step completes
logger.info(f"[WEBHOOK] Workflow step {step_id} completed")
logger.info(f"[WEBHOOK] Querying object_workflow_mapping for step_id={step_id}")

# After query
logger.info(f"[WEBHOOK] Found {len(mappings)} workflow mappings")
for mapping in mappings:
    logger.info(f"[WEBHOOK]   - {mapping.object_type} {mapping.object_id} action={mapping.action}")

# Query notification configs
logger.info(f"[WEBHOOK] Querying push_notification_configs")
logger.info(f"[WEBHOOK] Found {len(configs)} notification configs")
for config in configs:
    logger.info(f"[WEBHOOK]   - id={config.id} url={config.url} active={config.is_active}")

# Before sending webhook
logger.info(f"[WEBHOOK] Preparing to send POST to {webhook_url}")

# After sending
logger.info(f"[WEBHOOK] POST sent, response status: {response.status_code}")

# On any failure
logger.error(f"[WEBHOOK] Failed: {error}", exc_info=True)
```

### 2. Verification Queries

Please run these queries after a test media buy creation:

```sql
-- Check if mapping exists
SELECT * FROM object_workflow_mapping
WHERE object_id = 'buy_TEST-XXXXX';

-- Check if notification config exists
SELECT * FROM push_notification_configs
WHERE url LIKE '%creative-status%'
ORDER BY created_at DESC LIMIT 1;

-- Check if step completed
SELECT step_id, status, completed_at FROM workflow_steps
WHERE step_id IN (
  SELECT step_id FROM object_workflow_mapping
  WHERE object_id = 'buy_TEST-XXXXX'
);

-- Check the join that webhook logic uses
SELECT
  m.object_type,
  m.object_id,
  m.action,
  s.status AS step_status,
  s.completed_at,
  c.url AS webhook_url,
  c.is_active
FROM object_workflow_mapping m
JOIN workflow_steps s ON m.step_id = s.step_id
CROSS JOIN push_notification_configs c
WHERE m.object_id = 'buy_TEST-XXXXX'
AND c.is_active = true;
```

### 3. Code Review Request

Please review the push notification trigger logic to confirm:
- Is it checking for `object_workflow_mapping` entries? ✅ (We know this from debug output)
- What happens after it finds the mapping?
- Are there additional validation checks?
- Is the webhook sending code actually being called?
- Are exceptions being caught and swallowed?

## Test Endpoint

We've verified the activation API webhook receiver works:

```bash
# This succeeds
curl -X POST http://localhost:3001/webhooks/creative-status/123/creative_TEST \
  -H "Content-Type: application/json" \
  -d '{
    "status": "active",
    "creative_id": "media_buy_TEST",
    "message": "Test webhook"
  }'

# Response: 200 OK
```

So the issue is **definitely on the sales agent side** - webhooks are never being sent.

## Timeline

- **2025-10-03**: Initial bug reported - `action` field was NULL
- **2025-10-04 00:00**: Sales agent team fixed `action` field ✅
- **2025-10-04 01:51**: Test shows `action='create'` correctly set ✅
- **2025-10-04 01:51**: Test shows workflow completes ✅
- **2025-10-04 01:51**: **Still no webhook sent** ❌

## Impact

- Activation API cannot track media buy activation completion
- Operations remain in "pending" state forever
- Manual intervention required to check media buy status
- No real-time notification of completion

## Workaround

Currently using timeout-based cleanup:
- Operations without progress for 5 minutes marked as "failed"
- Not ideal - assumes failure when media buy may have succeeded

## Next Steps

1. Sales agent team adds debug logging
2. Sales agent team reviews webhook sending logic
3. Run test again with enhanced logging
4. Identify exact point where webhook sending fails
5. Fix and verify

---

**Files for Reference**:
- Previous bug report: `WEBHOOK_BUG_UPDATE.md`
- Test results: `WEBHOOK_TEST_RESULTS.md`
- Test script: `scripts/test-real-webhook-flow.ts`
