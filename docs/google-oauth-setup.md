# Google OAuth Setup for Admin UI

The AdCP Sales Agent Admin UI now uses Google OAuth2 for secure authentication, replacing the previous password-based system.

**Quick Start**: See [OAuth Quick Setup Guide](oauth-quick-setup.md) for step-by-step instructions.

## Features

- **Google Sign-In**: Users authenticate with their Google accounts
- **Email-based Authorization**: Control access via email addresses or domains
- **Role-based Access**: Super admins can manage all tenants, tenant admins only their own
- **Multi-tenant Support**: Users can have access to multiple tenants

## Prerequisites

- Google OAuth 2.0 credentials configured with the correct redirect URI
- Docker or Python 3.12+ environment
- Access to modify environment variables

## Setup Instructions

### 1. Google OAuth Credentials

The OAuth credentials file is already provided:
- `client_secret_1002878641006-1balq5ha6fq3fq58bsho78gst2da4e6u.apps.googleusercontent.com.json`

**Important**: The redirect URI must be configured in Google Cloud Console as:
```
http://localhost:8001/auth/google/callback
```

If you need to add or update this redirect URI:
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to APIs & Services → Credentials
3. Find your OAuth 2.0 Client ID
4. Add `http://localhost:8001/auth/google/callback` to Authorized redirect URIs
5. Save the changes

### 2. Super Admin Configuration

Configure super admin access via environment variables:

```bash
# Option 1: Specific email addresses
export SUPER_ADMIN_EMAILS="admin@example.com,cto@example.com"

# Option 2: Email domains (anyone with this domain)
export SUPER_ADMIN_DOMAINS="example.com,company.com"

# You can use both options together
```

### 3. Tenant Admin Configuration

Each tenant's configuration includes authorization settings:

```json
{
  "tenant_id": "example_tenant",
  "config": {
    "authorized_emails": [
      "admin@tenant.com",
      "manager@tenant.com"
    ],
    "authorized_domains": [
      "tenant.com"
    ],
    // ... other config
  }
}
```

### 4. Running the OAuth Admin UI

```bash
# Install dependencies
uv sync

# Set super admin configuration (optional)
export SUPER_ADMIN_EMAILS="your-email@example.com"

# Run the OAuth-enabled admin UI (on port 8001 to match redirect URI)
python admin_ui_oauth.py
```

## Authentication Flow

1. User visits `http://localhost:8001`
2. Clicks "Sign in with Google"
3. Authenticates with Google
4. System checks:
   - Is email a super admin? → Full access
   - Is email authorized for specific tenant(s)? → Tenant access
   - Otherwise → Access denied

## User Experience

### For Super Admins
- Access URL: `http://localhost:8001/`
- Sign in with authorized Google account
- Access all tenants and features
- Create/manage tenants
- Configure tenant authorization

### For Tenant Admins
- Access URL: `http://localhost:8001/tenant/YOUR_TENANT_ID/login`
- Sign in with authorized Google account
- Access only their tenant
- Cannot see or modify other tenants
- Cannot create new tenants
- Direct tenant access without tenant selection

### Multiple Tenant Access
If a user has access to multiple tenants:
1. After Google sign-in, they see a tenant selection page
2. Choose which tenant to manage
3. Can switch tenants by logging out and back in

## Authorization Management

### Adding Users to a Tenant

Super admins can add users in two ways:

1. **Specific Emails**: Add individual email addresses
   ```json
   "authorized_emails": ["user1@example.com", "user2@example.com"]
   ```

2. **Domain Authorization**: Allow all users from a domain
   ```json
   "authorized_domains": ["partner.com"]
   ```

### Security Considerations

- OAuth credentials should be kept secure
- Regularly review authorized users
- Remove access for departed employees
- Use domain authorization carefully
- Consider using corporate domains for super admin access

## Troubleshooting

### "Email not authorized" error
- Check if email is in tenant's authorized_emails
- Check if email domain is in authorized_domains
- For super admin access, check environment variables

### OAuth redirect error
- Ensure you're accessing via `http://localhost:8001`
- Verify the redirect URI in Google Cloud Console is exactly: `http://localhost:8001/auth/google/callback`
- The redirect URI is case-sensitive and must match exactly
- If using a different port, update both the Docker configuration and Google OAuth settings

### No super admins configured
- Set `SUPER_ADMIN_EMAILS` or `SUPER_ADMIN_DOMAINS` environment variables
- Restart the admin UI after setting variables