# PR #797 Deployment Guide

## Overview

**PR**: [#797 - Fix landing page not showing for custom domains](https://github.com/adcontextprotocol/salesagent/pull/797)

**What Changed**: Landing page routing logic to support unlimited custom domains via database lookup instead of hardcoded domain suffixes.

**Risk Level**: Medium
- Changes core routing logic
- Affects all landing pages
- Could impact MCP/A2A endpoint routing if something goes wrong

**Rollback Time**: < 2 minutes

## Pre-Deployment Checklist

### 1. Verify Tests Pass
```bash
# In workspace directory
./run_all_tests.sh ci

# Should see:
# ✅ Unit tests passed (1021 passed)
# ✅ Integration tests passed (35 passed)
# ✅ Integration_v2 tests passed (15 passed)
```

### 2. Capture Baseline
```bash
# Test production endpoints before deploy
python scripts/test_production_landing_pages.py > baseline_before_deploy.txt
```

Expected output: All tests should pass (or note any existing issues)

### 3. Review Changes
```bash
# Review the actual code changes
git diff origin/main HEAD src/core/main.py
```

Key changes:
- Line 649-660: Host header detection (apx_host + host_header fallback)
- Line 657: Debug logging
- Line 663-684: Custom domain routing (database lookup, no hardcoded domains)
- Line 686-717: Subdomain routing (unchanged logic)
- Line 677, 708: Error handling with generate_fallback_landing_page

## Deployment Steps

### 1. Merge PR
```bash
# Merge via GitHub UI or:
gh pr merge 797 --squash
```

This will trigger auto-deploy to Fly.io (takes ~2-3 minutes)

### 2. Monitor Deploy
```bash
# Watch deployment progress
fly status --app adcp-sales-agent

# Watch logs for errors
fly logs --app adcp-sales-agent
```

Look for:
- `[LANDING]` log entries showing host detection
- No errors during startup
- Application healthy

### 3. Wait for Propagation
Wait 2 minutes after deploy completes for:
- Fly.io instances to update
- DNS/CDN caches to clear
- Health checks to pass

## Post-Deployment Verification

### 1. Run Test Script (Critical)
```bash
# Test all production endpoints
python scripts/test_production_landing_pages.py
```

Expected results:
```
✓ accuweather.sales-agent.scope3.com - Landing Page
✓ accuweather.sales-agent.scope3.com - MCP Endpoint
✓ accuweather.sales-agent.scope3.com - A2A Endpoint
✓ accuweather.sales-agent.scope3.com - Agent Card
✓ applabs.sales-agent.scope3.com - Landing Page
✓ applabs.sales-agent.scope3.com - MCP Endpoint
✓ applabs.sales-agent.scope3.com - A2A Endpoint
✓ applabs.sales-agent.scope3.com - Agent Card
✓ test-agent.adcontextprotocol.org - Landing Page
✓ test-agent.adcontextprotocol.org - MCP Endpoint
✓ test-agent.adcontextprotocol.org - A2A Endpoint
✓ test-agent.adcontextprotocol.org - Agent Card
✓ admin.sales-agent.scope3.com - Admin Redirect

All tests passed (13/13)
```

### 2. Manual Browser Tests

**Test accuweather.sales-agent.scope3.com:**
1. Open https://accuweather.sales-agent.scope3.com
2. Verify: Shows proper landing page (not generic fallback)
3. Verify: MCP endpoint link present
4. Verify: A2A documentation link present
5. Verify: Agent card link present (.well-known/agent.json)
6. Click MCP link → should go to /mcp endpoint (not 404)

**Test applabs.sales-agent.scope3.com:**
1. Open https://applabs.sales-agent.scope3.com
2. Same checks as above

**Test admin.sales-agent.scope3.com:**
1. Open https://admin.sales-agent.scope3.com
2. Verify: Redirects to login page (not landing page)

### 3. Check Debug Logs
```bash
# Look for landing page requests
fly logs --app adcp-sales-agent | grep "\[LANDING\]"
```

Expected format:
```
[LANDING] apx_host=accuweather.sales-agent.scope3.com, host_header=accuweather.sales-agent.scope3.com:443, effective_host=accuweather.sales-agent.scope3.com
```

Verify:
- `apx_host` is set for Approximated requests
- `effective_host` is correct
- No errors after logging

## Success Criteria

✅ All tests pass in test script
✅ AccuWeather domain shows proper landing page
✅ Testing subdomain shows proper landing page
✅ Admin domain redirects to login
✅ MCP endpoints accessible
✅ A2A endpoints accessible
✅ Agent cards accessible
✅ No errors in logs for 15 minutes

## If Tests Fail - ROLLBACK IMMEDIATELY

```bash
# Option 1: Fly.io rollback (fastest - 30 seconds)
fly releases --app adcp-sales-agent
fly releases rollback --app adcp-sales-agent <previous-release>

# Option 2: Git revert
git revert -m 1 <merge-commit>
git push origin main
```

See [ROLLBACK_PROCEDURE.md](./ROLLBACK_PROCEDURE.md) for detailed instructions.

## Monitoring Period

Monitor for 15-30 minutes after successful deployment:

```bash
# Watch error rate
fly logs --app adcp-sales-agent | grep -i error

# Watch landing page requests
fly logs --app adcp-sales-agent | grep "\[LANDING\]"

# Re-run test script every 5 minutes
watch -n 300 'python scripts/test_production_landing_pages.py'
```

## What Could Go Wrong

### Most Likely Issues:

1. **Tenant not configured with virtual_host**
   - Symptom: Custom domain shows fallback instead of landing page
   - Fix: Update tenant record in database
   - Rollback: Not needed if other domains work

2. **Host header missing in some requests**
   - Symptom: Some requests show "No host specified" fallback
   - Fix: Check Approximated proxy configuration
   - Rollback: Probably needed if widespread

3. **Database lookup fails**
   - Symptom: All custom domains show fallback
   - Fix: Check database connectivity
   - Rollback: Immediately

### Unlikely Issues:

4. **Route registration breaks**
   - Symptom: 404 on all endpoints
   - Fix: Check for route conflicts
   - Rollback: Immediately

5. **Admin UI breaks**
   - Symptom: Admin domain shows landing page
   - Fix: Check `is_sales_agent_domain()` logic
   - Rollback: Immediately

## Communication Plan

### If Rollback Needed:

1. Post in Slack:
   ```
   🚨 Rolling back PR #797 (landing page changes)
   Issue: [describe what broke]
   ETA: 2 minutes
   Status: [link to status page if available]
   ```

2. Create incident doc:
   ```bash
   # docs/incidents/2025-11-26-pr-797-rollback.md
   ```

3. Update PR with findings

### If Deploy Successful:

1. Post in Slack:
   ```
   ✅ PR #797 deployed successfully
   - All landing pages working
   - All endpoints accessible
   - Monitoring for next 30 minutes
   ```

2. Update PR with deployment confirmation

## Questions?

- Check logs: `fly logs --app adcp-sales-agent`
- Run tests: `python scripts/test_production_landing_pages.py`
- See rollback guide: `docs/deployment/ROLLBACK_PROCEDURE.md`
