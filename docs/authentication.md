# Authentication Guide for AdCP Sales Agent

## Overview

The AdCP Sales Agent uses token-based authentication for both MCP and A2A protocols. Authentication is enforced at multiple levels to ensure secure access to advertising operations.

## Authentication Flow

```
Client Request
    ↓
Protocol Layer (MCP/A2A)
    ↓
Extract x-adcp-auth header
    ↓
Validate against Database
    ↓
Check principals table → Check tenants.admin_token
    ↓
Grant access or reject
```

## Token Types

### 1. Principal Tokens
- **Purpose**: Standard API access for advertisers/buyers
- **Storage**: `principals.access_token` column
- **Scope**: Limited to assigned tenant
- **Example**: `principal_abc123_token`

### 2. Admin Tokens  
- **Purpose**: Administrative operations within a tenant
- **Storage**: `tenants.admin_token` column (in config JSON)
- **Scope**: Full access to tenant operations
- **Example**: `admin_tenant1_secret`

### 3. Super Admin Access
- **Purpose**: System-wide administration
- **Access**: Via Admin UI with OAuth
- **Configuration**: `SUPER_ADMIN_EMAILS` environment variable

## Authentication Headers

### Required Header
```http
x-adcp-auth: your_access_token
```

### Optional Headers
```http
x-adcp-tenant: tenant_id  # Explicit tenant selection
```

## Multi-Tenant Routing

Tenants can be identified through:

1. **Explicit Header**: `x-adcp-tenant: sports`
2. **Subdomain**: `sports.adcp-sales-agent.fly.dev`
3. **Default**: Falls back to "default" tenant

## Database Schema

### Principals Table
```sql
CREATE TABLE principals (
    tenant_id VARCHAR(50),
    principal_id VARCHAR(100),
    name VARCHAR(255),
    access_token VARCHAR(255) UNIQUE,
    platform_mappings JSONB,
    created_at TIMESTAMP
);
```

### Tenants Table
```sql
CREATE TABLE tenants (
    tenant_id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255),
    config JSONB,  -- Contains admin_token
    billing_plan VARCHAR(50)
);
```

## Setting Up Authentication

### 1. Create a Tenant
```bash
docker exec -it adcp-server python setup_tenant.py "Publisher Name" \
  --adapter mock
```

This generates:
- Tenant ID
- Admin token (stored in config)
- Default products

### 2. Create a Principal
```python
# Via Admin UI or directly in database
INSERT INTO principals (
    tenant_id, 
    principal_id, 
    name, 
    access_token,
    platform_mappings
) VALUES (
    'sports',
    'advertiser_001',
    'Example Advertiser',
    'secure_token_xyz123',
    '{"google_ad_manager": {"advertiser_id": "12345"}}'
);
```

### 3. Use the Token

#### MCP Protocol
```python
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

headers = {"x-adcp-auth": "secure_token_xyz123"}
transport = StreamableHttpTransport(
    url="http://localhost:8080/mcp/", 
    headers=headers
)
client = Client(transport=transport)
```

#### A2A Protocol
```python
import httpx

headers = {
    "Content-Type": "application/json",
    "x-adcp-auth": "secure_token_xyz123"
}

request = {
    "jsonrpc": "2.0",
    "method": "get_products",
    "params": {},
    "id": 1
}

response = httpx.post(
    "http://localhost:8090/rpc",
    json=request,
    headers=headers
)
```

## Production Deployment

### Environment Variables
```bash
# Required for Admin UI
SUPER_ADMIN_EMAILS=admin@company.com
SUPER_ADMIN_DOMAINS=company.com

# OAuth for Admin UI
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=xxx
```

### Security Best Practices

1. **Never commit tokens** to version control
2. **Use strong tokens**: At least 32 characters, cryptographically random
3. **Rotate tokens regularly**: Implement token rotation policy
4. **Audit all access**: All operations are logged with principal_id
5. **Use HTTPS in production**: Never send tokens over unencrypted connections
6. **Limit token scope**: Create separate principals for different use cases

## Token Generation

### Secure Token Generation (Python)
```python
import secrets
import string

def generate_secure_token(length=32):
    """Generate a cryptographically secure token."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

# Example
token = generate_secure_token(48)
print(f"New token: {token}")
```

### Bash Alternative
```bash
# Generate secure token
openssl rand -base64 32 | tr -d "=+/" | cut -c1-32
```

## Troubleshooting

### Common Issues

1. **401 Unauthorized**
   - Check token is correct
   - Verify tenant_id matches
   - Ensure token hasn't been revoked

2. **403 Forbidden**
   - Principal may lack permissions
   - Check platform_mappings configuration

3. **Token Not Found**
   - Verify database connection
   - Check if migrations have run
   - Ensure tenant exists

### Debug Authentication
```sql
-- Check if token exists
SELECT * FROM principals WHERE access_token = 'your_token';

-- Check tenant configuration
SELECT tenant_id, config->>'admin_token' as admin_token 
FROM tenants WHERE tenant_id = 'your_tenant';

-- View recent authentication attempts
SELECT * FROM audit_logs 
WHERE operation = 'authenticate' 
ORDER BY timestamp DESC LIMIT 10;
```

## API Rate Limiting

While not currently implemented, production deployments should consider:

1. **Per-token rate limits**: Track requests per principal
2. **Tenant-level quotas**: Enforce billing plan limits
3. **Global rate limiting**: Protect against DDoS

## Audit Logging

All authenticated operations are logged:

```sql
SELECT 
    timestamp,
    principal_id,
    operation,
    success,
    details
FROM audit_logs
WHERE tenant_id = 'sports'
ORDER BY timestamp DESC;
```

## Next Steps

1. **Implement OAuth2**: For more sophisticated token management
2. **Add API key rotation**: Automated key rotation with overlap period
3. **Implement rate limiting**: Protect against abuse
4. **Add webhook authentication**: For async callbacks
5. **Support JWT tokens**: For stateless authentication