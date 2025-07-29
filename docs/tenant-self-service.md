# Tenant Self-Service in Admin UI

The AdCP Sales Agent Admin UI now supports tenant self-service, allowing tenants to log in and manage their own instances in a multi-tenant deployment.

## Features

### 1. Role-Based Authentication

The system supports two types of users:
- **Super Admin**: Can manage all tenants, create new tenants, and access all functionality
- **Tenant Admin**: Can only view and manage their own tenant's configuration

### 2. Login System

The login page (`/login`) now accepts:
- **Username**: Either `admin` for super admin or the `tenant_id` for tenant admins
- **Password**: 
  - Super admin: Uses `ADMIN_UI_PASSWORD` environment variable (default: `admin`)
  - Tenant admin: Uses the `admin_token` from their tenant configuration

### 3. Access Control

The system enforces strict access control:
- Tenant admins are automatically redirected to their own tenant detail page
- Tenant admins cannot access other tenants' pages
- Only super admins can create new tenants
- The navigation menu adapts based on user role

### 4. Visual Indicators

The UI clearly shows:
- Current username in the header
- User role (Super Admin badge or tenant name badge)
- Appropriate navigation options based on role

## Configuration

Each tenant's configuration includes an `admin_token` field that serves as their admin password:

```json
{
  "tenant_id": "example_tenant",
  "config": {
    "admin_token": "secure_random_token_here",
    // ... other config
  }
}
```

## Usage

### For Super Admins
1. Navigate to `http://localhost:8081/login`
2. Enter username: `admin`
3. Enter password: (from `ADMIN_UI_PASSWORD` env var)
4. Access all tenants and create new ones

### For Tenant Admins
1. Navigate to `http://localhost:8081/login`
2. Enter username: Your `tenant_id`
3. Enter password: Your `admin_token` from configuration
4. Manage your tenant's settings, principals, and products

## Security

- Sessions are secured with Flask's session management
- Admin tokens are generated using `secrets.token_urlsafe(32)`
- Failed login attempts show generic error messages
- All routes require authentication
- Role-based permissions are enforced at the route level