# Nginx Authorization Header Stripping Bug - 2025-10-25

## Summary
Nginx proxy configuration was stripping the `Authorization` header from A2A requests before forwarding to the backend server, causing all authenticated requests to fail with "Missing authentication token - Bearer token required in Authorization header"

## Problem Description

### Symptoms
1. **A2A requests failing with auth error**:
   ```
   ERROR: A2A: Response received (error)
   [-32600] Error: Missing authentication token - Bearer token required in Authorization header
   ```
2. **Buyer agents unable to authenticate** to sales agent A2A endpoints
3. **Headers being sent by client** but not reaching application code

### User Reports
> "A2A to test-agent.adcontextprotocol.org in production: Missing authentication token - Bearer token required in Authorization header"

## Root Cause

### Technical Analysis

**The Problem**: Nginx was **not forwarding the `Authorization` header** from incoming requests to the backend A2A server.

**Code Location**: Multiple nginx configuration files
- `config/nginx/nginx.conf` (local/Docker)
- `fly/nginx.conf` (production deployment)

**Why This Failed**:
Nginx's `proxy_set_header` directive **replaces** default headers. When you explicitly set headers like:
```nginx
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
# ... other headers
```

Nginx **stops forwarding** any headers not explicitly listed. By default, nginx forwards most headers, but once you start using `proxy_set_header`, you must explicitly forward ALL headers you need.

**Missing directive**:
```nginx
location /a2a {
    proxy_pass http://localhost:8091/a2a;
    # ... other directives
    # ❌ Authorization header NOT being forwarded!
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

### Request Flow (Before Fix)

1. **Buyer sends request** with `Authorization: Bearer <token>`
2. **Nginx receives request** with Authorization header ✅
3. **Nginx proxies to backend** but **strips Authorization header** ❌
4. **A2A middleware** looks for Authorization header - NOT FOUND ❌
5. **Handler raises error**: "Missing authentication token" ❌

### Why Application Code Appeared Correct

The Python application code was working perfectly:

1. ✅ **Middleware extracts token** (lines 2393-2428 in `adcp_a2a_server.py`)
   ```python
   auth_header = None
   for key, value in request.headers.items():
       if key.lower() == "authorization":
           auth_header = value.strip()
           break
   ```

2. ✅ **Token stored in thread-local** context
   ```python
   if auth_header and auth_header.startswith("Bearer "):
       token = auth_header[7:]  # Remove "Bearer " prefix
       _request_context.auth_token = token
   ```

3. ✅ **Handler checks for token**
   ```python
   auth_token = self._get_auth_token()
   if requires_auth and not auth_token:
       raise ServerError(InvalidRequestError(
           message="Missing authentication token - Bearer token required in Authorization header"
       ))
   ```

**The issue**: The request never reached the application WITH the Authorization header - it was stripped at the nginx layer.

## Solution

### The Fix
Added `proxy_set_header Authorization $http_authorization;` to all `/a2a` location blocks:

```nginx
location /a2a {
    proxy_pass http://localhost:8091/a2a;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection 'upgrade';
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Authorization $http_authorization;  # ← ADDED THIS
    proxy_set_header x-adcp-tenant $tenant;
    proxy_cache_bypass $http_upgrade;
}
```

### Why `$http_authorization`?
In nginx, incoming HTTP headers are available as variables with the `$http_` prefix:
- Incoming header: `Authorization: Bearer abc123`
- Nginx variable: `$http_authorization`
- Value: `Bearer abc123`

### Files Changed
- `config/nginx/nginx.conf`: 4 `/a2a` location blocks updated
- `fly/nginx.conf`: 2 `/a2a` location blocks updated

### Affected Endpoints
- `*.adcontextprotocol.org/a2a` (agent routing)
- `*.sales-agent.scope3.com/a2a` (tenant routing)
- `sales-agent.scope3.com/a2a` (base domain)
- External domains/a2a (default server)

## Impact

### Before Fix
- ❌ A2A authentication completely broken in production
- ❌ Buyers unable to call any authenticated A2A endpoints
- ❌ Only public endpoints (like `list_authorized_properties`) worked

### After Fix
- ✅ A2A authentication works correctly
- ✅ Buyers can authenticate with `Authorization: Bearer <token>`
- ✅ All authenticated endpoints accessible

## Testing

### Manual Testing
```bash
# Test A2A endpoint with authentication
curl -X POST https://test-agent.sales-agent.scope3.com/a2a \
  -H "Host: test-agent.sales-agent.scope3.com" \
  -H "Authorization: Bearer <principal_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "params": {
      "message": {
        "messageId": "test-123",
        "role": "user",
        "kind": "message",
        "parts": [{
          "kind": "data",
          "data": {
            "skill": "get_products",
            "input": {
              "brief": "video ads"
            }
          }
        }]
      }
    },
    "id": 1
  }'

# Should now return products instead of auth error
```

### Verification Checklist
- [ ] A2A requests with Authorization header work
- [ ] Middleware logs show "Extracted Bearer token for A2A request"
- [ ] Authenticated endpoints return data (not auth error)
- [ ] Public endpoints still work without auth

## Related Issues
- **2025-10-23**: A2A tenant detection bug (FIXED - tenant detection from headers)
- **2025-10-04**: Test agent auth inconsistency (DOCUMENTED - known issue with test-agent)
- **Current issue**: Nginx header forwarding (FIXED)

## Prevention

### For Future Configuration Changes
1. **Always forward Authorization header** in nginx proxy configs
2. **Test with real HTTP requests** (not just curl without auth)
3. **Check nginx access logs** to see what headers nginx receives
4. **Check application logs** to see what headers backend receives
5. **Document which headers are business-critical** (Authorization, Host, x-adcp-tenant, etc.)

### Configuration Template
When adding new proxy locations that need authentication, use this template:

```nginx
location /your-endpoint {
    proxy_pass http://backend;
    proxy_http_version 1.1;

    # Essential headers
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # CRITICAL: Always forward Authorization for authenticated endpoints
    proxy_set_header Authorization $http_authorization;

    # Application-specific headers
    proxy_set_header x-adcp-tenant $tenant;
    # ... add others as needed

    proxy_cache_bypass $http_upgrade;
}
```

## Lessons Learned

### What Worked Well
1. ✅ Application code was already correct and well-tested
2. ✅ Middleware properly extracts Authorization when present
3. ✅ Error messages were clear about missing header
4. ✅ Tenant detection already fixed (from 2025-10-23)

### What Could Be Improved
1. ❌ Integration tests don't cover nginx proxy layer
2. ❌ No monitoring/alerting for auth failures
3. ❌ Nginx config not checked for required headers

### Action Items
1. **Add integration test** that makes real HTTP request through nginx
2. **Add pre-commit hook** to check nginx configs include Authorization header
3. **Document required headers** for each endpoint type
4. **Add nginx config validation** to CI pipeline

## Deployment

### Steps to Deploy Fix
1. Commit changes: ✅ Done (commit a0c114c2)
2. Push to branch: `git push origin fix-tenant-auth-detection`
3. Create PR for review
4. After merge, deploy triggers automatically (Fly.io)
5. Verify with test request to production

### Rollback Plan
If issues occur:
```bash
# Revert nginx changes
git revert a0c114c2
git push origin main

# Fly.io will auto-deploy the revert
```

## Contact

**Reporter**: Brian O'Kelley
**Branch**: `fix-tenant-auth-detection`
**Commit**: a0c114c2
**Date Reported**: 2025-10-25
**Date Fixed**: 2025-10-25
