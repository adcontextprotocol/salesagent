# Fly.io Deployment

This walkthrough covers deploying the AdCP Sales Agent to Fly.io. The reference implementation at https://adcp-sales-agent.fly.dev uses this setup.

> **Single-Tenant by Default**: Fly.io deployments run in single-tenant mode by default, which is appropriate for most publishers deploying their own sales agent. Session cookies use the actual request domain, so authentication works with any custom domain. For multi-tenant mode with subdomain routing, see [Multi-Tenant Setup](../multi-tenant.md).

> **Template**: A ready-to-use `fly.toml` template is available at [`fly.toml.template`](fly.toml.template). Copy it to your project root and customize.

## Prerequisites

1. [Fly.io account](https://fly.io)
2. Fly CLI installed: `brew install flyctl` (macOS) or see [installation docs](https://fly.io/docs/hands-on/install-flyctl/)

## Step 1: Authenticate

```bash
fly auth login
```

## Step 2: Create Application

```bash
fly apps create your-app-name
```

## Step 3: Create PostgreSQL Database

```bash
# Create PostgreSQL cluster
fly postgres create --name your-app-db \
  --region iad \
  --initial-cluster-size 1 \
  --vm-size shared-cpu-1x \
  --volume-size 10

# Attach to your app (automatically sets DATABASE_URL)
fly postgres attach your-app-db --app your-app-name
```

Verify DATABASE_URL is set:
```bash
fly secrets list --app your-app-name
```

## Step 4: Set Required Secrets

```bash
# Super admin configuration (required)
fly secrets set SUPER_ADMIN_EMAILS="admin@example.com,admin2@example.com"

# Optional: Grant admin to all users in a domain
fly secrets set SUPER_ADMIN_DOMAINS="example.com"
```

**Format for admin configuration:**
- `SUPER_ADMIN_EMAILS`: Comma-separated, no spaces: `user1@example.com,user2@example.com`
- `SUPER_ADMIN_DOMAINS`: Comma-separated domains: `example.com,company.org`

### Authentication Options

Choose one of these authentication methods:

**Option A: Quick Start with Test Mode** (for evaluation/testing)
```bash
fly secrets set ADCP_AUTH_TEST_MODE="true"
```
This enables test login buttons that bypass OAuth. Not for production.

**Option B: Generic OIDC** (Okta, Auth0, Azure AD, Keycloak, etc.)
```bash
fly secrets set OAUTH_DISCOVERY_URL="https://your-provider.com/.well-known/openid-configuration"
fly secrets set OAUTH_CLIENT_ID="your-client-id"
fly secrets set OAUTH_CLIENT_SECRET="your-client-secret"
```
Add redirect URI to your provider: `https://your-app-name.fly.dev/auth/google/callback`

**Option C: Google OAuth**
```bash
fly secrets set GOOGLE_CLIENT_ID="your-client-id.apps.googleusercontent.com"
fly secrets set GOOGLE_CLIENT_SECRET="your-client-secret"
```
Add redirect URI to [Google OAuth credentials](https://console.cloud.google.com/apis/credentials): `https://your-app-name.fly.dev/auth/google/callback`

## Step 5: Deploy

```bash
fly deploy
```

The first deploy runs database migrations automatically. Watch the logs:
```bash
fly logs
```

## Step 6: Verify

```bash
# Check health
curl https://your-app-name.fly.dev/health

# Check status
fly status --app your-app-name
```

## Accessing Services

| Service | URL |
|---------|-----|
| Admin UI | https://your-app-name.fly.dev/admin |
| MCP Server | https://your-app-name.fly.dev/mcp/ |
| Health Check | https://your-app-name.fly.dev/health |

> **Authentication**: Visiting `/admin` without being logged in will redirect you to the login page. After successful authentication, you'll be redirected back to the Admin UI.

## Monitoring

```bash
# View logs
fly logs

# Check status
fly status

# SSH into machine
fly ssh console

# Open dashboard
fly dashboard
```

## Scaling

```bash
# Horizontal scaling
fly scale count 2 --region iad

# Vertical scaling
fly scale vm shared-cpu-2x
fly scale memory 2048
```

## Troubleshooting

### Database connection issues

```bash
# Verify DATABASE_URL is set
fly secrets list --app your-app-name | grep DATABASE

# Check if postgres is attached
fly postgres list

# Test database connectivity
fly ssh console --app your-app-name -C "python -c \"from src.core.database.db_config import get_db_connection; print(get_db_connection())\""
```

### Migrations not running

Migrations run automatically on startup. To run manually:
```bash
fly ssh console --app your-app-name -C "cd /app && python scripts/ops/migrate.py"
```

### Super admin access not working

1. Verify the secret is set correctly:
   ```bash
   fly ssh console --app your-app-name -C "echo \$SUPER_ADMIN_EMAILS"
   ```

2. Check format (must be comma-separated, no spaces around commas):
   - Correct: `user1@example.com,user2@example.com`
   - Wrong: `["user1@example.com"]` (JSON array)
   - Wrong: `user1@example.com, user2@example.com` (spaces)

3. Restart to pick up changes:
   ```bash
   fly apps restart your-app-name
   ```

### Force restart

```bash
fly apps restart your-app-name
```

## Configuration Files

The deployment uses these files from the repository:
- `fly.toml` - Main Fly.io configuration
- `Dockerfile` - Docker image with nginx and supercronic
- `scripts/deploy/run_all_services.py` - Service orchestration

## Costs

- **shared-cpu-1x VM**: ~$5/month
- **PostgreSQL shared-cpu-1x**: ~$7/month
- **Volume storage**: ~$0.15/GB/month

Total for a basic deployment: ~$12-15/month
