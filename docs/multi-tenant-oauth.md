# Multi-Tenant OAuth Configuration

The AdCP Admin UI supports multi-tenant OAuth authentication with path-based routing, making it easy to provide tenant-specific login URLs while using a single Google OAuth application.

## Overview

Each tenant gets their own login URL:
- Super Admin: `http://localhost:8001/`
- Tenant-specific: `http://localhost:8001/tenant/{tenant_id}/login`

This allows:
- Direct tenant access without selection screens
- Tenant branding on login pages
- Clear separation between super admin and tenant access
- Easy sharing of tenant-specific URLs

## Google OAuth Configuration

### Redirect URIs

Since Google OAuth doesn't support wildcard redirect URIs, you need to add each tenant's callback URL individually:

1. **Super Admin Callback**:
   ```
   http://localhost:8001/auth/google/callback
   ```

2. **Per-Tenant Callbacks** (add for each tenant):
   ```
   http://localhost:8001/tenant/default/auth/google/callback
   http://localhost:8001/tenant/sports/auth/google/callback
   http://localhost:8001/tenant/news/auth/google/callback
   ```

### Adding New Tenants

When you create a new tenant, remember to:
1. Add its redirect URI to Google OAuth configuration
2. Wait a few minutes for Google to propagate the change
3. Share the tenant-specific login URL with authorized users

## Tenant Configuration

Each tenant's authorization is configured in their database record:

```json
{
  "tenant_id": "sports",
  "config": {
    "authorized_emails": [
      "admin@sportspublisher.com",
      "editor@sportspublisher.com"
    ],
    "authorized_domains": [
      "sportspublisher.com"
    ]
  }
}
```

## Access Patterns

### Direct Tenant Access
```
User → http://localhost:8001/tenant/sports/login
     → Sign in with Google
     → Direct access to sports tenant
```

### Super Admin Access
```
User → http://localhost:8001/
     → Sign in with Google
     → Dashboard with all tenants
     → Can access any tenant
```

### Mixed Access
If a user is both a super admin and has specific tenant access:
- Via `/`: Full super admin access
- Via `/tenant/xxx/login`: Limited to that specific tenant

## Security Considerations

1. **Tenant Isolation**: Users authenticated via tenant-specific URLs can only access that tenant
2. **URL Security**: Tenant login URLs should only be shared with authorized users
3. **Redirect URI Validation**: Google enforces exact redirect URI matching for security
4. **Session Scope**: Sessions are scoped to include the tenant context

## Implementation Details

The system uses Flask session management to track:
- `role`: Either 'super_admin' or 'tenant_admin'
- `tenant_id`: Which tenant the user can access (for tenant admins)
- `email`: The authenticated user's email
- `username`: The user's display name

## Troubleshooting

### "Redirect URI mismatch" for new tenant
- Ensure you've added the exact tenant callback URL to Google OAuth
- Format: `http://localhost:8001/tenant/{exact_tenant_id}/auth/google/callback`
- URLs are case-sensitive

### User can't access tenant
- Verify their email is in the tenant's `authorized_emails` list
- Or their domain is in `authorized_domains`
- Check the tenant is active in the database

### Session conflicts
- Users should log out before switching between super admin and tenant access
- Clear browser cookies if experiencing issues

## Best Practices

1. **Naming Conventions**: Use consistent tenant IDs (lowercase, no spaces)
2. **Documentation**: Document each tenant's authorized users
3. **Regular Audits**: Review tenant access lists periodically
4. **URL Management**: Keep a registry of tenant login URLs
5. **Redirect URI Limits**: Google has a limit on redirect URIs per OAuth app (~100)

## Future Enhancements

For production deployments with many tenants, consider:
1. Using subdomains instead of paths (requires DNS configuration)
2. Implementing a proxy OAuth service to handle dynamic redirects
3. Using multiple OAuth apps for different tenant groups