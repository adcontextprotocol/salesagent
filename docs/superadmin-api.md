# Super Admin API Documentation

The Super Admin API provides programmatic access to manage tenants in the AdCP Sales Agent server. This API is designed for integration with the main Scope3 application to automate tenant provisioning.

## Authentication

All API endpoints (except the initial key generation) require authentication via the `X-Superadmin-API-Key` header.

### Initialize API Key (One-time Setup)

```bash
POST /api/v1/superadmin/init-api-key
```

This endpoint can only be called once to generate the super admin API key. The key is stored in the database and cannot be retrieved again.

**Response:**
```json
{
  "message": "Super admin API key initialized",
  "api_key": "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "warning": "Save this key securely. It cannot be retrieved again."
}
```

## Endpoints

### Health Check

```bash
GET /api/v1/superadmin/health
Headers: X-Superadmin-API-Key: <your-api-key>
```

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-01-06T12:00:00.000000"
}
```

### List Tenants

```bash
GET /api/v1/superadmin/tenants
Headers: X-Superadmin-API-Key: <your-api-key>
```

**Response:**
```json
{
  "tenants": [
    {
      "tenant_id": "tenant_abc123",
      "name": "Sports Publisher",
      "subdomain": "sports",
      "is_active": true,
      "billing_plan": "standard",
      "ad_server": "google_ad_manager",
      "created_at": "2025-01-06T12:00:00.000000",
      "adapter_configured": true
    }
  ],
  "count": 1
}
```

### Create Tenant

```bash
POST /api/v1/superadmin/tenants
Headers: X-Superadmin-API-Key: <your-api-key>
Content-Type: application/json
```

**Required Fields:**
- `name` - Publisher/tenant name
- `subdomain` - Unique subdomain for tenant access
- `ad_server` - Ad server type: `google_ad_manager`, `kevel`, `triton`, or `mock`

**Optional Fields:**
- `gam_refresh_token` - OAuth refresh token (for GAM)
- `gam_network_code` - GAM network code (can be configured later in UI)
- `authorized_emails` - Array of authorized admin emails
- `authorized_domains` - Array of authorized email domains
- `billing_plan` - Billing plan (default: "standard")
- `create_default_principal` - Create default API principal (default: true)
- Other adapter-specific fields

**Example - Minimal GAM Tenant (refresh token only):**
```json
{
  "name": "Sports Publisher",
  "subdomain": "sports",
  "ad_server": "google_ad_manager",
  "gam_refresh_token": "1//0gxxxxxxxxxxxxxx"
}
```

**Example - Full GAM Configuration:**
```json
{
  "name": "News Publisher",
  "subdomain": "news",
  "ad_server": "google_ad_manager",
  "gam_network_code": "123456789",
  "gam_refresh_token": "1//0gxxxxxxxxxxxxxx",
  "gam_company_id": "company_123",
  "gam_trafficker_id": "trafficker_456",
  "authorized_emails": ["admin@newspublisher.com"],
  "authorized_domains": ["newspublisher.com"],
  "billing_plan": "premium",
  "create_default_principal": true
}
```

**Response:**
```json
{
  "tenant_id": "tenant_xyz789",
  "name": "News Publisher",
  "subdomain": "news",
  "admin_token": "admin_token_here",
  "admin_ui_url": "http://news.localhost:8001/tenant/tenant_xyz789",
  "default_principal_token": "principal_token_here"
}
```

### Get Tenant Details

```bash
GET /api/v1/superadmin/tenants/<tenant_id>
Headers: X-Superadmin-API-Key: <your-api-key>
```

**Response:**
```json
{
  "tenant_id": "tenant_xyz789",
  "name": "News Publisher",
  "subdomain": "news",
  "is_active": true,
  "billing_plan": "premium",
  "ad_server": "google_ad_manager",
  "created_at": "2025-01-06T12:00:00.000000",
  "settings": {
    "max_daily_budget": 10000,
    "enable_aee_signals": true,
    "authorized_emails": ["admin@newspublisher.com"],
    "authorized_domains": ["newspublisher.com"],
    "human_review_required": true
  },
  "adapter_config": {
    "adapter_type": "google_ad_manager",
    "gam_network_code": "123456789",
    "has_refresh_token": true,
    "gam_company_id": "company_123",
    "gam_trafficker_id": "trafficker_456"
  },
  "principals_count": 1
}
```

### Update Tenant

```bash
PUT /api/v1/superadmin/tenants/<tenant_id>
Headers: X-Superadmin-API-Key: <your-api-key>
Content-Type: application/json
```

**Request Body (all fields optional):**
```json
{
  "name": "Updated News Publisher",
  "billing_plan": "enterprise",
  "max_daily_budget": 50000,
  "adapter_config": {
    "gam_refresh_token": "new_refresh_token",
    "gam_company_id": "new_company_id"
  }
}
```

### Delete Tenant

```bash
DELETE /api/v1/superadmin/tenants/<tenant_id>?hard_delete=false
Headers: X-Superadmin-API-Key: <your-api-key>
```

By default, this performs a soft delete (sets `is_active=false`). To permanently delete, use `?hard_delete=true`.

## Integration Flow for Scope3 App

Here's the recommended integration flow for the Scope3 application:

1. **User initiates setup:**
   - User clicks "Add AdCP Media Agent"
   - Selects "Set one up for me"
   - Chooses "Google Ad Manager"

2. **OAuth Flow:**
   - Display Google OAuth button
   - User completes OAuth flow
   - Capture the refresh token

3. **Create Tenant via API:**
   
   **Option A - Minimal Setup (Recommended):**
   ```javascript
   // Just provide the refresh token, let publisher configure the rest in Admin UI
   const response = await fetch('https://adcp-server.example.com/api/v1/superadmin/tenants', {
     method: 'POST',
     headers: {
       'X-Superadmin-API-Key': SUPERADMIN_API_KEY,
       'Content-Type': 'application/json'
     },
     body: JSON.stringify({
       name: companyName,
       subdomain: generateSubdomain(companyName),
       ad_server: 'google_ad_manager',
       gam_refresh_token: refreshToken // From OAuth
     })
   });
   
   const tenant = await response.json();
   ```
   
   **Option B - Full Configuration:**
   ```javascript
   // Configure everything via API
   const response = await fetch('https://adcp-server.example.com/api/v1/superadmin/tenants', {
     method: 'POST',
     headers: {
       'X-Superadmin-API-Key': SUPERADMIN_API_KEY,
       'Content-Type': 'application/json'
     },
     body: JSON.stringify({
       name: companyName,
       subdomain: generateSubdomain(companyName),
       ad_server: 'google_ad_manager',
       gam_network_code: networkCode, // From OAuth or user input
       gam_refresh_token: refreshToken, // From OAuth
       authorized_emails: [userEmail],
       authorized_domains: [emailDomain],
       create_default_principal: true
     })
   });
   
   const tenant = await response.json();
   ```

4. **Redirect to Admin UI:**
   - Store the `tenant_id` and `default_principal_token` in your database
   - Redirect user to `tenant.admin_ui_url`
   - SSO will allow the user to access their provisioned tenant

## Error Handling

All error responses follow this format:
```json
{
  "error": "Error message here"
}
```

Common HTTP status codes:
- `400` - Bad Request (missing required fields)
- `401` - Unauthorized (missing or invalid API key)
- `404` - Not Found (tenant doesn't exist)
- `409` - Conflict (e.g., subdomain already exists)
- `500` - Internal Server Error

## Security Considerations

1. **API Key Storage:** Store the super admin API key securely (e.g., in environment variables or a secure vault)
2. **HTTPS:** Always use HTTPS in production
3. **Rate Limiting:** Consider implementing rate limiting for the API
4. **Audit Logging:** All API operations are logged in the audit_logs table
5. **Refresh Token Security:** GAM refresh tokens are sensitive - ensure secure transmission and storage