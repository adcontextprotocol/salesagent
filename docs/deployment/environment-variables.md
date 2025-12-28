# Environment Variables Reference

Complete reference for all environment variables supported by the AdCP Sales Agent.

## Quick Start

For a minimal working deployment:

```bash
# Required
DATABASE_URL=postgresql://user:password@host:5432/adcp
SUPER_ADMIN_EMAILS=admin@example.com

# Authentication (choose one)
ADCP_AUTH_TEST_MODE=true  # For testing only
# OR
GOOGLE_CLIENT_ID=...      # For production
GOOGLE_CLIENT_SECRET=...
```

## Authentication

### Test Mode

| Variable | Default | Description |
|----------|---------|-------------|
| `ADCP_AUTH_TEST_MODE` | `false` | Enable test authentication with pre-configured accounts. **Not for production.** |

When enabled, provides test login buttons with these accounts:
- Super Admin: `test_super_admin@example.com` / `test123`
- Tenant Admin: `test_tenant_admin@example.com` / `test123`
- Tenant User: `test_tenant_user@example.com` / `test123`

### OAuth - Generic OIDC

Works with Okta, Auth0, Azure AD, Keycloak, and any OIDC-compliant provider.

| Variable | Default | Description |
|----------|---------|-------------|
| `OAUTH_DISCOVERY_URL` | - | OIDC discovery URL (e.g., `https://provider.com/.well-known/openid-configuration`) |
| `OAUTH_CLIENT_ID` | - | OAuth client ID |
| `OAUTH_CLIENT_SECRET` | - | OAuth client secret |
| `OAUTH_SCOPES` | `openid email profile` | OAuth scopes to request |
| `OAUTH_PROVIDER` | `google` | Provider name for display purposes |

### OAuth - Google

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_CLIENT_ID` | - | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | - | Google OAuth client secret |
| `GOOGLE_OAUTH_REDIRECT_URI` | auto | Custom redirect URI (usually auto-detected) |

### Access Control

| Variable | Default | Description |
|----------|---------|-------------|
| `SUPER_ADMIN_EMAILS` | - | **Required.** Comma-separated list of super admin emails |
| `SUPER_ADMIN_DOMAINS` | - | Comma-separated domains (grants admin to all users from these domains) |

Format: `user1@example.com,user2@example.com` (no spaces)

---

## Database

### Connection

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | - | **Required.** Full PostgreSQL connection URL |

Or use individual variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | `localhost` | Database host |
| `DB_PORT` | `5432` | Database port |
| `DB_NAME` | `adcp` | Database name |
| `DB_USER` | `adcp` | Database user |
| `DB_PASSWORD` | - | Database password |
| `DB_SSLMODE` | `prefer` | PostgreSQL SSL mode |

### Connection Pool

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_QUERY_TIMEOUT` | `30` | Query timeout in seconds |
| `DATABASE_CONNECT_TIMEOUT` | `10` | Connection timeout in seconds |
| `DATABASE_POOL_TIMEOUT` | `30` | Pool checkout timeout in seconds |
| `USE_PGBOUNCER` | `false` | Enable PgBouncer connection pooling mode |

### Migrations

| Variable | Default | Description |
|----------|---------|-------------|
| `SKIP_MIGRATIONS` | `false` | Skip automatic migrations on startup |

---

## AI Features

AI features (creative review, product suggestions) are configured **per-tenant** in the Admin UI. Each tenant sets their own Gemini API key.

### Observability

| Variable | Default | Description |
|----------|---------|-------------|
| `LOGFIRE_TOKEN` | - | Logfire observability token for AI tracing |

---

## Google Ad Manager (GAM)

For GAM adapter integration:

| Variable | Default | Description |
|----------|---------|-------------|
| `GAM_OAUTH_CLIENT_ID` | - | GAM OAuth client ID (separate from admin OAuth) |
| `GAM_OAUTH_CLIENT_SECRET` | - | GAM OAuth client secret |
| `GCP_PROJECT_ID` | - | GCP project ID for service account management |
| `GOOGLE_APPLICATION_CREDENTIALS` | - | Path to GCP service account JSON file |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | - | GCP service account credentials as JSON string |

---

## Multi-Tenant Mode

| Variable | Default | Description |
|----------|---------|-------------|
| `ADCP_MULTI_TENANT` | `false` | Enable multi-tenant mode with subdomain routing |
| `SALES_AGENT_DOMAIN` | - | Base domain for tenant subdomains (e.g., `sales-agent.example.com`) |
| `BASE_DOMAIN` | - | Top-level domain for cookies (e.g., `example.com`) |

---

## Environment & Deployment

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | `development` | `development` (strict validation) or `production` (lenient) |
| `PRODUCTION` | `false` | Set to `true` for production deployments |
| `ADMIN_UI_URL` | `http://localhost:8001` | Public URL for Admin UI (used in notifications) |

### Demo Data

| Variable | Default | Description |
|----------|---------|-------------|
| `CREATE_DEMO_TENANT` | `true` | Create "Default Publisher" tenant with mock adapter on startup |
| `CREATE_SAMPLE_DATA` | `false` | Create sample products, media buys, etc. |

### Security

| Variable | Default | Description |
|----------|---------|-------------|
| `ENCRYPTION_KEY` | auto-generated | Key for encrypting sensitive data in database |
| `FLASK_SECRET_KEY` | dev key | Flask session secret (auto-generated in production) |
| `WEBHOOK_SECRET` | - | Secret for verifying incoming webhooks |

---

## External Integrations

| Variable | Default | Description |
|----------|---------|-------------|
| `APPROXIMATED_API_KEY` | - | Approximated proxy service API key |

---

## Development & Debugging

| Variable | Default | Description |
|----------|---------|-------------|
| `FLASK_DEBUG` | `0` | Enable Flask debug mode |
| `FLASK_ENV` | `production` | Flask environment |
| `ADCP_DRY_RUN` | `false` | Run operations without making actual changes |
| `ADCP_TESTING` | `false` | Enable testing mode (internal) |

### Service Startup

| Variable | Default | Description |
|----------|---------|-------------|
| `SKIP_NGINX` | `false` | Skip nginx in deployment scripts |
| `SKIP_CRON` | `false` | Skip cron job scheduling |

---

## Categorized Summary

### Secrets (set via `fly secrets set` or secure vault)

These contain sensitive credentials and should never be in config files:

- `DATABASE_URL`
- `ENCRYPTION_KEY`
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
- `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`
- `GAM_OAUTH_CLIENT_ID`, `GAM_OAUTH_CLIENT_SECRET`
- `GOOGLE_APPLICATION_CREDENTIALS_JSON`
- `APPROXIMATED_API_KEY`
- `WEBHOOK_SECRET`
- `FLASK_SECRET_KEY`

### Environment Variables (can be in fly.toml, docker-compose, etc.)

Non-sensitive configuration:

- `ENVIRONMENT`, `PRODUCTION`
- `ADCP_MULTI_TENANT`, `BASE_DOMAIN`, `SALES_AGENT_DOMAIN`
- `ADMIN_UI_URL`, `GOOGLE_OAUTH_REDIRECT_URI`
- `CREATE_DEMO_TENANT`
- `SKIP_NGINX`, `SKIP_CRON`

### Variables with Sensible Defaults (usually don't need to set)

- All `DB_*` individual variables (use `DATABASE_URL` instead)
- All `*_PORT` variables (hardcoded in nginx)
- `DATABASE_*_TIMEOUT` variables
- `PYDANTIC_AI_*` variables
- `OAUTH_SCOPES`
