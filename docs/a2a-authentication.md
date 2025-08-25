# A2A Server Authentication

The AdCP A2A server requires authentication to ensure tenant isolation and security. Since the standard `a2a` CLI from python-a2a doesn't support authentication headers, we provide a custom client script.

## Authentication Methods

The A2A server accepts authentication tokens via:
1. **Authorization header**: `Bearer <token>`
2. **Custom header**: `X-Auth-Token: <token>`
3. **Query parameter**: `?token=<token>` (for compatibility)

## Using the Authenticated Client

### Installation

The authenticated client script is located at `scripts/a2a_auth_client.py` and requires no additional dependencies beyond what's already installed.

### Basic Usage

```bash
# Local server
uv run python scripts/a2a_auth_client.py http://localhost:8091 "your message" --token YOUR_TOKEN

# Production server
uv run python scripts/a2a_auth_client.py https://adcp-sales-agent.fly.dev/a2a "your message" --token YOUR_TOKEN
```

### Examples

```bash
# List available products
uv run python scripts/a2a_auth_client.py http://localhost:8091 "list available products" --token demo_token_123

# Get pricing information
uv run python scripts/a2a_auth_client.py http://localhost:8091 "show me pricing for display ads" --token demo_token_123

# Check targeting options
uv run python scripts/a2a_auth_client.py http://localhost:8091 "what targeting options are available?" --token demo_token_123

# Get raw JSON response
uv run python scripts/a2a_auth_client.py http://localhost:8091 "help" --token demo_token_123 --json
```

## Getting Authentication Tokens

Authentication tokens are managed per-principal (advertiser) in the database:

1. **Via Admin UI**:
   - Navigate to http://localhost:8001
   - Go to "Advertisers" section
   - View or create advertisers to see their tokens

2. **Via Database**:
   ```sql
   -- List all principals and their tokens
   SELECT tenant_id, principal_id, name, access_token
   FROM principals;
   ```

3. **Demo Token** (local development only):
   - Token: `demo_token_123`
   - Principal: `demo_principal`
   - Tenant: `demo_publisher`

## Troubleshooting

### Authentication Failed
- **Error**: "Authentication failed. Please check your token."
- **Solution**: Verify the token exists in the principals table for the correct tenant

### Endpoint Not Found
- **Error**: "Endpoint not found: ..."
- **Solution**:
  - For local: Use `http://localhost:8091` (not `/a2a`)
  - For production: Use `https://adcp-sales-agent.fly.dev/a2a`

### Connection Failed
- **Error**: "Failed to connect to ..."
- **Solution**: Ensure the A2A server is running:
  ```bash
  # Check if running locally
  docker-compose ps

  # Check production status
  fly status --app adcp-sales-agent
  ```

## Security Notes

- Tokens are validated against the database on every request
- Each token is tied to a specific principal (advertiser) and tenant (publisher)
- Invalid tokens receive a 401 Unauthorized response
- The server logs all authentication attempts for audit purposes

## Standard a2a CLI (Unauthenticated)

The standard `a2a` CLI from python-a2a doesn't support authentication headers. Attempting to use it with our authenticated server will fail:

```bash
# This will NOT work with authentication enabled
a2a send https://adcp-sales-agent.fly.dev/a2a "hello"
# Error: Receives 401 Unauthorized
```

Use the `scripts/a2a_auth_client.py` script instead for all authenticated requests.
