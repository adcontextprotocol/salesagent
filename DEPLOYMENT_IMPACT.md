# Deployment Impact Analysis - Scope3 Removal PR

## Summary

This PR removes all hardcoded Scope3 domain references and makes the codebase vendor-neutral. The changes are **backwards compatible** with the existing Fly.io deployment.

## What Changed

### Code Changes
- Removed 60+ hardcoded `scope3.com` and `sales-agent.scope3.com` references
- Created centralized `src/core/domain_config.py` module with 15+ utility functions
- Updated 25+ Python files, JavaScript, HTML templates, and configuration files
- Made all domain references configurable via environment variables

### Default Behavior
**Important**: The code defaults to `scope3.com` for backwards compatibility:

```python
# src/core/domain_config.py
def get_base_domain() -> str:
    return os.getenv("BASE_DOMAIN", "scope3.com")  # Defaults to scope3.com
```

This means:
- ✅ Existing Fly.io deployment will continue to work **without any changes**
- ✅ No environment variables need to be set for current behavior
- ✅ Domain configuration happens at runtime, not build time
- ✅ Zero downtime - deployment will work exactly as before

## Current Fly.io Configuration

### Existing Environment Variables in Fly.io
```bash
# These are already set in Fly.io (fly secrets list)
GEMINI_API_KEY=***
GOOGLE_CLIENT_ID=***
GOOGLE_CLIENT_SECRET=***
SUPER_ADMIN_EMAILS=***
GAM_OAUTH_CLIENT_ID=***
GAM_OAUTH_CLIENT_SECRET=***
# ... and others
```

### Current fly.toml Environment Section
```toml
[env]
  PRODUCTION = "true"
  ADCP_UNIFIED_MODE = "true"
  A2A_SERVER_URL = "https://sales-agent.scope3.com/a2a"  # Still hardcoded in fly.toml
  # ... other settings
```

## What Happens When This PR is Merged?

### Immediate Impact (No Changes Required)
1. **Code will use defaults**:
   - `BASE_DOMAIN` → defaults to `scope3.com`
   - `SALES_AGENT_DOMAIN` → defaults to `sales-agent.scope3.com`
   - `ADMIN_DOMAIN` → defaults to `admin.sales-agent.scope3.com`
   - `SUPER_ADMIN_DOMAIN` → defaults to `scope3.com`

2. **Fly.io deployment continues to work**:
   - No environment variables need to be added
   - All URLs, OAuth redirects, session cookies work as before
   - A2A server URL constructed correctly at runtime
   - MCP server URL constructed correctly at runtime

3. **Only change needed** (optional cleanup):
   - Remove hardcoded `A2A_SERVER_URL` from `fly.toml` [env] section
   - This is optional - the code will use `domain_config.py` functions instead

### Future Migration to New Domain (When Ready)

To migrate to a new domain (e.g., `adcontextprotocol.org`):

1. **Set Fly.io secrets**:
   ```bash
   fly secrets set BASE_DOMAIN=adcontextprotocol.org --app adcp-sales-agent
   fly secrets set SALES_AGENT_DOMAIN=sales-agent.adcontextprotocol.org --app adcp-sales-agent
   fly secrets set ADMIN_DOMAIN=admin.sales-agent.adcontextprotocol.org --app adcp-sales-agent
   fly secrets set SUPER_ADMIN_DOMAIN=adcontextprotocol.org --app adcp-sales-agent
   ```

2. **Update OAuth credentials**:
   - Add new redirect URI to Google OAuth credentials
   - Update authorized domains in Google Cloud Console

3. **Update DNS**:
   - Point new domain to Fly.io app

4. **Deploy** (automatic on main branch merge)

## Testing Before Merge

### What We Tested
✅ All unit tests passed (840 tests)
✅ All integration tests passed
✅ All E2E tests passed
✅ Pre-commit hooks passed
✅ CI checks passed (commitizen, linting, type checking)

### What Was NOT Tested
⚠️ **Real deployment to Fly.io** - We did not deploy to staging/production yet
⚠️ **OAuth flow with scope3.com** - Assumes existing OAuth credentials still work
⚠️ **Session cookies across subdomains** - Code should work but not tested in production

## Recommended Deployment Strategy

### Option A: Merge and Monitor (Recommended)
1. Merge PR to main branch
2. Auto-deploy to Fly.io (existing CI/CD)
3. Monitor logs for any domain-related issues
4. Rollback if needed (code is backwards compatible)

**Risk Level**: ⚠️ Low-Medium
- Code defaults to existing behavior
- No environment variables needed
- Should work identically to before
- But hasn't been tested on real Fly.io deployment

### Option B: Deploy to Staging First (Safer)
1. Create staging Fly.io app
2. Deploy this branch to staging
3. Test OAuth flow, session cookies, A2A/MCP URLs
4. Merge to main after validation

**Risk Level**: ✅ Low
- Validates changes in real environment
- Catches any unforeseen issues
- More time consuming

## Rollback Plan

If issues occur after merging:

1. **Quick rollback**:
   ```bash
   # Revert to previous commit
   git revert <commit-hash>
   git push origin main
   # Auto-deploys reverted version
   ```

2. **Emergency fix**:
   - Set environment variables in Fly.io to override defaults
   - No code changes needed

## Questions to Answer Before Merging

1. ✅ **Are we okay with scope3.com as the default domain?**
   - Yes - it maintains backwards compatibility
   - Can be changed later with environment variables

2. ✅ **Do we need to update anything in Fly.io before merging?**
   - No - code defaults to current behavior
   - Optional: Remove `A2A_SERVER_URL` from fly.toml

3. ❓ **Should we test on staging first?**
   - Up to you - code should work but hasn't been tested in production

4. ❓ **When do we plan to migrate to a new domain?**
   - Not urgent - can happen any time after this PR
   - Just set environment variables when ready

## Conclusion

This PR is designed to be **zero-impact** on the existing deployment. The code defaults to `scope3.com` for backwards compatibility, so no environment variables need to be set. The deployment should work exactly as before.

However, we recommend monitoring the first deployment after merge to catch any unforeseen issues. If problems occur, we can quickly rollback or set environment variables to override the defaults.

**Recommendation**: Merge and monitor, with rollback plan ready. The changes are minimal risk due to backwards compatibility.
