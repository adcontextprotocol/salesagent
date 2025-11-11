# Security & Authentication

## Admin Authentication Architecture

The admin authentication system uses an **environment-first approach** with database fallback for robust, secure access control.

### Current Implementation

```python
def is_super_admin(email):
    """Environment-first authentication with database fallback."""
    # 1. Check environment variables first (deployment-time config)
    env_emails = os.environ.get("SUPER_ADMIN_EMAILS", "")
    if env_emails:
        emails_list = [e.strip().lower() for e in env_emails.split(",") if e.strip()]
        if email.lower() in emails_list:
            return True

    # 2. Fallback to database configuration (runtime config)
    try:
        with get_db_session() as db:
            config = db.query(TenantManagementConfig).filter_by(
                config_key="super_admin_emails"
            ).first()
            if config and config.config_value:
                db_emails = [e.strip().lower() for e in config.config_value.split(",")]
                return email.lower() in db_emails
    except Exception as e:
        logger.error(f"Database auth check failed: {e}")

    return False
```

### Session Optimization

- **Session Caching**: Super admin status cached in session to avoid redundant database calls
- **Trust Session State**: `require_tenant_access()` checks session first, then validates if needed
- **Automatic Caching**: Session updated when admin status is confirmed

## Security Recommendations for Future Enhancement

### HIGH Priority

#### 1. Session Timeout & Re-validation
```python
# Add to require_tenant_access decorator
max_session_age = 3600  # 1 hour
session_start = session.get("authenticated_at", 0)
if time.time() - session_start > max_session_age:
    session.clear()
    return redirect(url_for("auth.login"))

# Re-validate admin status every 5 minutes
last_check = session.get("admin_check_at", 0)
if time.time() - last_check > 300:
    session["is_super_admin"] = is_super_admin(email)
    session["admin_check_at"] = time.time()
```

#### 2. Enhanced Audit Logging
```python
def audit_admin_access(email, tenant_id, action, success=True):
    """Log all admin access attempts with IP and user agent."""
    audit_log = AuditLog(
        email=email,
        tenant_id=tenant_id,
        action=f"admin_access_{action}",
        success=success,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string,
        timestamp=datetime.utcnow()
    )
```

### MEDIUM Priority

#### 3. Secure Session Configuration
```python
app.config.update(
    SESSION_COOKIE_SECURE=True,      # HTTPS only
    SESSION_COOKIE_HTTPONLY=True,    # No JavaScript access
    SESSION_COOKIE_SAMESITE='Lax',   # CSRF protection
    PERMANENT_SESSION_LIFETIME=3600  # 1 hour timeout
)
```

#### 4. Secrets Management
Move from `.env` files to proper secrets management:
- Fly.io secrets for production
- Kubernetes secrets for k8s deployments
- AWS Secrets Manager or similar for AWS

## Tenant Registration Security

### Subdomain Assignment
To prevent subdomain squatting and brand impersonation, tenant subdomains are **automatically generated** using random UUIDs.

**Implementation**:
- Subdomains are 8-character hexadecimal strings (e.g., `a7f3d92b`)
- Generated from UUID4 (first 8 characters)
- Users cannot choose custom subdomains during signup
- Eliminates risk of claiming subdomains like "nytimes" or "cnn"

**Branding Solution**:
Publishers who want branded URLs should use **virtual hosts** (custom domains):
- Configure custom domain (e.g., `sales.publisher.com`) in tenant settings
- Domain ownership verified by Approximated proxy service
- Proper branding without security risks

**Ad Server Configuration Check**:
Tenants without configured ad servers show a "Pending Configuration" page instead of active agent endpoints. This prevents incomplete registrations from appearing operational.

## Access Control Patterns

### Super Admins
- Full access to all tenants
- Configured via environment variables or database
- Can create/modify/delete tenants and users

### Tenant Users
- Limited access to specific tenants via User model
- Cannot access other tenants' data
- Can manage their own tenant's configuration

### Principal Isolation
- Each advertiser (principal) has isolated access tokens
- Tokens scoped to specific tenant
- Cannot access other tenants or principals

### Audit Trail
- All admin actions logged to `audit_logs` table
- Includes timestamp, user, action, and result
- Used for compliance and security monitoring

## Security Testing Requirements

All authentication changes must include tests for:
- Session timeout behavior
- Re-validation logic
- Environment vs database precedence
- Audit logging completeness
- Session security headers
- CSRF protection

**Test Location**: `tests/integration/test_product_deletion.py` contains comprehensive authentication tests including environment-first approach validation.

## OAuth Cross-Domain Authentication

### Current Implementation Status
**✅ Working**: OAuth authentication works correctly within the `sales-agent.scope3.com` domain and its subdomains.

**⚠️ Known Limitation**: OAuth authentication from external domains (e.g., `test-agent.adcontextprotocol.org`) has limitations due to browser cookie security restrictions.

### How OAuth Currently Works

#### Same-Domain OAuth (✅ Fully Functional)
- User visits `https://tenant.sales-agent.scope3.com/admin/`
- OAuth flow works perfectly with session cookies
- User redirected back to tenant subdomain after authentication

#### Cross-Domain OAuth (⚠️ Limited)
- User visits external domain (e.g., `https://test-agent.adcontextprotocol.org/admin/`)
- OAuth initiation works and stores external domain in session
- OAuth callback cannot retrieve session data due to cookie domain restrictions
- User redirected to login page instead of back to external domain

### Technical Details

#### Session Cookie Configuration
```python
# Production session config
SESSION_COOKIE_DOMAIN = ".sales-agent.scope3.com"  # Scoped to internal domain
SESSION_COOKIE_SECURE = True                        # HTTPS only
SESSION_COOKIE_SAMESITE = "None"                   # Required for OAuth
SESSION_COOKIE_PATH = "/admin/"                     # Admin interface only
```

#### OAuth Flow Architecture
```python
# OAuth Initiation (stores external domain in session)
session["oauth_external_domain"] = request.headers.get("Apx-Incoming-Host")

# OAuth Callback (retrieves from session - fails cross-domain)
external_domain = session.pop("oauth_external_domain", None)
```

### Browser Security Limitation
The limitation is due to fundamental browser security: **cookies cannot be shared across different domains**. When a user comes from `test-agent.adcontextprotocol.org`, the browser cannot access session cookies scoped to `.sales-agent.scope3.com`.

### Test Coverage
- ✅ OAuth session handling within same domain
- ✅ Approximated header detection and processing
- ✅ Session cookie configuration
- ✅ Redirect URI integrity (no modifications)
- ✅ CSRF protection preservation (Authlib state management)
- ✅ Cross-domain limitation documentation

**Key Test File**: `tests/integration/test_oauth_session_handling.py`

### Future Solutions (Research Needed)
Potential approaches for cross-domain OAuth:
1. **Alternative State Storage**: Redis, database, or external service
2. **Modified Redirect URI Approach**: Register additional redirect URIs with domain-specific query parameters
3. **Authentication Architecture Changes**: Different authentication flow for external domains
4. **Proxy-Based Solution**: Handle authentication at the proxy/gateway level

### Current Recommendation
For immediate needs, direct users to use `https://tenant.sales-agent.scope3.com/admin/` for OAuth authentication rather than external domain URLs.

## Secrets Configuration

### .env.secrets File (REQUIRED)
**🔒 Security**: All secrets MUST be in `.env.secrets` file (no environment variables).

Create `/Users/brianokelley/Developer/salesagent/.env.secrets`:

```bash
# API Keys
GEMINI_API_KEY=your-gemini-api-key-here

# OAuth Configuration (for Admin UI)
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
SUPER_ADMIN_EMAILS=user1@example.com,user2@example.com

# GAM OAuth Configuration (required for Google Ad Manager functionality)
GAM_OAUTH_CLIENT_ID=your-gam-client-id.apps.googleusercontent.com
GAM_OAUTH_CLIENT_SECRET=your-gam-client-secret

# Optional
SUPER_ADMIN_DOMAINS=example.com
```

### Why .env.secrets?
- **Single Source**: All secrets in one place
- **Gitignore Protection**: File not committed to repository
- **Workspace Isolation**: Each workspace can have different secrets
- **Reduced Risk**: No accidental secret exposure via environment variables

### Security Best Practices
1. **Never commit secrets** to version control
2. **Use different secrets** for dev/staging/production
3. **Rotate secrets regularly** (at least quarterly)
4. **Audit secret access** via logs
5. **Use secrets managers** in production (Fly.io secrets, AWS Secrets Manager, etc.)
