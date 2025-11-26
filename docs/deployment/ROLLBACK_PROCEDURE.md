# Rollback Procedure

## When to Rollback

Roll back if ANY of these conditions are met after deployment:

- ✗ Landing pages not showing for custom domains
- ✗ MCP endpoints returning errors
- ✗ A2A endpoints not accessible
- ✗ Agent cards not loading
- ✗ Admin UI login broken
- ✗ More than 10% of production traffic getting errors

## Quick Rollback (< 2 minutes)

### Option 1: Git Revert (Recommended)

```bash
# On your local machine
cd /path/to/salesagent

# Find the commit to revert (the merge commit of PR #797)
git log --oneline -10

# Revert the merge commit
git revert -m 1 <merge-commit-hash>

# Push to trigger auto-deploy
git push origin main
```

### Option 2: Fly.io Rollback (Fastest)

```bash
# List recent releases
fly releases --app adcp-sales-agent

# Rollback to previous release (before PR #797)
fly releases rollback --app adcp-sales-agent <release-number>
```

### Option 3: Manual Deploy Previous Commit

```bash
# Checkout previous commit
git checkout <commit-before-merge>

# Deploy directly
fly deploy --app adcp-sales-agent
```

## Verification After Rollback

Run the test script to verify rollback was successful:

```bash
python scripts/test_production_landing_pages.py
```

All tests should pass after rollback.

## Post-Rollback Actions

1. **Document the issue**:
   - What broke?
   - Error messages/logs
   - Which domains were affected?

2. **Create incident report**:
   ```bash
   # Create file: docs/incidents/2025-XX-XX-landing-page-rollback.md
   ```

3. **Fix in development**:
   - Create new branch
   - Fix the issue
   - Test thoroughly locally
   - Re-deploy to staging first

4. **Update PR**:
   - Add fixes to PR #797
   - Request re-review
   - Deploy again when ready

## Monitoring During Deploy

### Before Deploy
```bash
# Baseline metrics
python scripts/test_production_landing_pages.py > before_deploy.txt
```

### After Deploy (wait 2 minutes for propagation)
```bash
# Test all endpoints
python scripts/test_production_landing_pages.py > after_deploy.txt

# Compare
diff before_deploy.txt after_deploy.txt
```

### Watch Logs
```bash
# Real-time logs
fly logs --app adcp-sales-agent

# Filter for errors
fly logs --app adcp-sales-agent | grep -i error

# Filter for landing page requests
fly logs --app adcp-sales-agent | grep "\[LANDING\]"
```

## Common Issues and Quick Fixes

### Issue: Custom domain shows fallback page

**Symptoms**:
- Generic "Landing Page Working" message
- No MCP/A2A links

**Quick Check**:
```bash
# Check if tenant exists
fly ssh console --app adcp-sales-agent
python -c "from src.core.config_loader import get_tenant_by_virtual_host; print(get_tenant_by_virtual_host('accuweather.sales-agent.scope3.com'))"
```

**Fix**: Tenant might not be configured with virtual_host
- Check database: tenant record has `virtual_host` field set
- May need to update tenant configuration

### Issue: MCP/A2A endpoints return 404

**Symptoms**:
- Landing page shows but endpoints don't work
- 404 errors on /mcp or / (A2A)

**Quick Check**:
```bash
curl -I https://accuweather.sales-agent.scope3.com/mcp
curl -X POST https://accuweather.sales-agent.scope3.com/ -H "Content-Type: application/json" -d '{}'
```

**Likely Cause**: Route registration issue (not caused by this PR)

### Issue: Admin login broken

**Symptoms**:
- Admin UI doesn't redirect to login
- Login page shows landing page instead

**Quick Check**:
```bash
curl -I https://admin.sales-agent.scope3.com/
# Should be 302/307 redirect to /auth/login
```

**Fix**: Likely route conflict (shouldn't be caused by this PR)

## Emergency Contacts

- **Primary**: Brian O'Kelley
- **Deployment Issues**: Check Fly.io status page
- **DNS Issues**: Check Approximated proxy status

## Deployment Checklist

Before merging PR #797:

- [ ] Run full test suite locally: `./run_all_tests.sh ci`
- [ ] Test script passes locally: `python scripts/test_production_landing_pages.py`
- [ ] PR approved by reviewer
- [ ] Ready to monitor deployment

After merging:

- [ ] Wait 2 minutes for auto-deploy
- [ ] Run test script: `python scripts/test_production_landing_pages.py`
- [ ] Check logs: `fly logs --app adcp-sales-agent | grep "\[LANDING\]"`
- [ ] Test each domain manually in browser
- [ ] Monitor for 15 minutes for errors

If ANY test fails:

- [ ] Roll back immediately using Option 2 (fastest)
- [ ] Document the issue
- [ ] Fix in development before re-deploying
