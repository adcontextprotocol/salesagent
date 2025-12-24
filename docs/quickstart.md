# Quickstart Guide

This guide walks you through deploying your own AdCP Sales Agent. Most publishers should follow the **single-tenant deployment** path - it's simpler and designed for running on your own domain.

## Deployment Options

| Option | Best For | Complexity |
|--------|----------|------------|
| **Docker Compose** | Local dev, on-premise | Low |
| **Cloud Run** | GCP users, serverless | Low |
| **Fly.io** | Simple cloud hosting | Low |
| **Kubernetes** | Enterprise, multi-region | Medium |

## Quick Start (Docker Compose)

The fastest way to get running locally:

```bash
# 1. Download the compose file
curl -O https://raw.githubusercontent.com/adcontextprotocol/salesagent/main/docker-compose.yml

# 2. Create environment file
cat > .env << 'EOF'
SUPER_ADMIN_EMAILS=your-email@example.com
GEMINI_API_KEY=your-gemini-key
EOF

# 3. Start services
docker compose up -d

# 4. Verify it's running
curl http://localhost:8000/health
```

Access the Admin UI at http://localhost:8000/admin

## What Gets Created

On first startup in single-tenant mode (the default):
- An empty "Default Publisher" tenant is created
- Super admins (from `SUPER_ADMIN_EMAILS`) get automatic access
- No demo data - you configure your real ad server

## Configuration Steps

### 1. Access Admin UI

Navigate to http://localhost:8000/admin and log in with Google OAuth (or test credentials in dev mode).

### 2. Configure Your Ad Server

Go to **Settings > Adapters** and configure your ad server:

- **Google Ad Manager (GAM)**: Enter your network code and OAuth credentials
- **Mock**: For testing without a real ad server

### 3. Set Up Products

Go to **Products** and create products that match your GAM line item templates.

### 4. Add Advertisers (Principals)

Go to **Advertisers** and add the advertisers who will use the MCP API.

### 5. Configure Your Domain (Production)

Go to **Settings > General** and set your **Virtual Host** (e.g., `sales-agent.yourcompany.com`).

Then configure DNS:
- Point your domain to your deployment
- The Admin UI shows the exact DNS records needed

## Cloud Run Deployment

Google Cloud Run works well for single-tenant deployments.

### Step 1: Create Cloud SQL PostgreSQL

Create a PostgreSQL instance using the cheapest sandbox option:

**[Create Cloud SQL Instance](https://console.cloud.google.com/sql/instances/create;engine=PostgreSQL;template=POSTGRES_ENTERPRISE_SANDBOX_TEMPLATE)**

After creation:
1. Note the **Connection name** (e.g., `my-project:us-central1:my-instance`)
2. Create a database named `adcp`
3. Create a user and password

### Step 2: Deploy in Test Mode

Deploy with test mode enabled - this lets you log in without OAuth:

```bash
# 1. Build and push to Google Container Registry
gcloud builds submit --tag gcr.io/YOUR_PROJECT/salesagent

# 2. Deploy to Cloud Run in test mode
gcloud run deploy salesagent \
  --image gcr.io/YOUR_PROJECT/salesagent \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8000 \
  --memory 1Gi \
  --add-cloudsql-instances YOUR_PROJECT:us-central1:YOUR_INSTANCE \
  --set-env-vars "ADCP_AUTH_TEST_MODE=true" \
  --set-env-vars "SUPER_ADMIN_EMAILS=your-email@example.com" \
  --set-env-vars "DATABASE_URL=postgresql://USER:PASSWORD@/adcp?host=/cloudsql/YOUR_PROJECT:us-central1:YOUR_INSTANCE" \
  --set-env-vars "GEMINI_API_KEY=your-gemini-key"
```

Note your service URL from the output (e.g., `https://salesagent-abc123-uc.a.run.app`)

### Step 3: Access Admin UI

Open `https://YOUR-CLOUDRUN-URL.run.app/admin` and log in using the test mode button. In test mode, the Google login button won't appear - you'll only see the test login option.

### Step 4: Add SSO/OAuth (for production)

Once you've verified the deployment works, add OAuth for production use. You can use **Google, Microsoft, Okta, Auth0**, or any OIDC-compliant provider.

**Option A: Google OAuth**

1. [Create OAuth credentials](https://console.cloud.google.com/auth/clients)
   - Click **"Create Credentials"** → **"OAuth client ID"**
   - Select **"Web application"**
   - Add **Authorized redirect URI**: `https://YOUR-CLOUDRUN-URL.run.app/auth/google/callback`

2. Update your deployment:
   ```bash
   gcloud run services update salesagent \
     --region us-central1 \
     --update-env-vars "GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com" \
     --update-env-vars "GOOGLE_CLIENT_SECRET=your-client-secret" \
     --remove-env-vars "ADCP_AUTH_TEST_MODE"
   ```

**Option B: Other OIDC Providers (Okta, Auth0, Azure AD, etc.)**

```bash
gcloud run services update salesagent \
  --region us-central1 \
  --update-env-vars "OAUTH_CLIENT_ID=your-client-id" \
  --update-env-vars "OAUTH_CLIENT_SECRET=your-client-secret" \
  --update-env-vars "OAUTH_DISCOVERY_URL=https://your-provider/.well-known/openid-configuration" \
  --remove-env-vars "ADCP_AUTH_TEST_MODE"
```

Users will be redirected directly to your SSO provider when they access `/login`.

### Optional: Custom Domain

```bash
gcloud beta run domain-mappings create \
  --service salesagent \
  --domain sales-agent.yourcompany.com \
  --region us-central1
```

If using a custom domain, add it as an additional redirect URI in your OAuth credentials.

**Cloud Run Requirements:**
- Cloud SQL PostgreSQL instance
- Port 8000 (nginx handles routing internally)
- At least 1GB memory recommended

## Fly.io Deployment

```bash
# 1. Install Fly CLI
brew install flyctl

# 2. Create app
fly apps create your-app-name

# 3. Create PostgreSQL
fly postgres create --name your-app-db
fly postgres attach your-app-db --app your-app-name

# 4. Set secrets
fly secrets set SUPER_ADMIN_EMAILS="your-email@example.com"
fly secrets set GEMINI_API_KEY="your-key"

# 5. Deploy (uses fly.toml from repo)
fly deploy
```

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `SUPER_ADMIN_EMAILS` | Comma-separated admin emails |

### Recommended

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | For AI-powered creative review |
| `GOOGLE_CLIENT_ID` | For Google OAuth login |
| `GOOGLE_CLIENT_SECRET` | For Google OAuth login |

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `ADCP_MULTI_TENANT` | Enable multi-tenant mode | `false` |
| `ENCRYPTION_KEY` | For encrypting sensitive data | Auto-generated |

## Single-Tenant vs Multi-Tenant

**Single-Tenant (Default)**
- One publisher per deployment
- Simple path-based routing (`/admin`, `/mcp`, `/a2a`)
- Set your custom domain in Admin UI settings
- No subdomain complexity

**Multi-Tenant**
- Multiple publishers on one deployment
- Subdomain-based routing (`publisher1.yourdomain.com`)
- Set `ADCP_MULTI_TENANT=true`
- Requires wildcard DNS and SSL

Most publishers should use single-tenant mode.

## Connecting AI Agents

Once deployed, AI agents connect via MCP:

```python
from fastmcp.client import Client, StreamableHttpTransport

# Get your endpoint and token from Admin UI > Settings > API & Tokens
transport = StreamableHttpTransport(
    url="https://sales-agent.yourcompany.com/mcp/",
    headers={"x-adcp-auth": "your-principal-token"}
)

async with Client(transport=transport) as client:
    # List available products
    products = await client.call_tool("get_products", {"brief": "video ads"})

    # Create a media buy
    result = await client.call_tool("create_media_buy", {
        "product_ids": ["prod_123"],
        "budget": {"amount": 10000, "currency": "USD"},
        "flight_start": "2024-02-01",
        "flight_end": "2024-02-28"
    })
```

## Troubleshooting

### "No tenant context" error
- Ensure `SUPER_ADMIN_EMAILS` includes your email
- Check that migrations ran successfully (`docker compose logs adcp-server`)

### OAuth redirect mismatch
- Add your domain to Google OAuth authorized redirect URIs
- Format: `https://your-domain.com/auth/google/callback`

### Database connection failed
- Verify `DATABASE_URL` is correct
- Ensure PostgreSQL is running and accessible
- Check firewall/security group rules

## Next Steps

- [Full Deployment Guide](deployment.md) - All deployment options in detail
- [GAM Adapter Setup](adapters/gam.md) - Configuring Google Ad Manager
- [API Reference](api.md) - MCP tool documentation
