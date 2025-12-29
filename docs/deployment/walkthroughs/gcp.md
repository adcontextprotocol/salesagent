# GCP Cloud Run Deployment

This walkthrough covers deploying the AdCP Sales Agent to Google Cloud Run with Cloud SQL PostgreSQL.

## Prerequisites

1. [Google Cloud Project](https://console.cloud.google.com) with billing enabled
2. [gcloud CLI](https://cloud.google.com/sdk/docs/install) installed and authenticated

## Step 1: Enable Required APIs

Enable the necessary GCP APIs:

```bash
gcloud services enable sqladmin.googleapis.com sql-component.googleapis.com run.googleapis.com
```

## Step 2: Create Cloud SQL PostgreSQL

Create a PostgreSQL instance (sandbox tier is fine for testing):

```bash
# Create instance
gcloud sql instances create adcp-sales-agent \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=us-central1 \
  --root-password=YOUR_SECURE_PASSWORD

# Create database
gcloud sql databases create salesagent --instance=adcp-sales-agent
```

Or use the [Cloud SQL Console](https://console.cloud.google.com/sql/instances/create;engine=PostgreSQL).

Note the **Connection name** from the instance overview (e.g., `your-project:us-central1:adcp-sales-agent`).

## Step 3: Deploy in Test Mode

Deploy with test mode enabled to verify everything works before configuring OAuth.

### Option A: Use Prebuilt Image (Recommended)

Fastest way to get started - uses the official Docker Hub image:

```bash
gcloud run deploy adcp-sales-agent \
  --image adcontextprotocol/salesagent:latest \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 1Gi \
  --port 8000 \
  --no-cpu-throttling \
  --min-instances=1 \
  --add-cloudsql-instances YOUR_PROJECT:us-central1:adcp-sales-agent \
  --set-env-vars "ADCP_AUTH_TEST_MODE=true" \
  --set-env-vars "SUPER_ADMIN_EMAILS=your-email@example.com" \
  --set-env-vars "DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@/salesagent?host=/cloudsql/YOUR_PROJECT:us-central1:adcp-sales-agent"
```

Replace:
- `YOUR_PROJECT`: Your GCP project ID
- `YOUR_PASSWORD`: The password you set when creating the Cloud SQL instance
- `your-email@example.com`: Your email address for super admin access

### Option B: Build Your Own Image

If you want to build from source or make custom modifications:

```bash
# Build and push image
gcloud builds submit --tag gcr.io/YOUR_PROJECT/adcp-sales-agent

# Deploy
gcloud run deploy adcp-sales-agent \
  --image gcr.io/YOUR_PROJECT/adcp-sales-agent \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 1Gi \
  --port 8000 \
  --no-cpu-throttling \
  --min-instances=1 \
  --add-cloudsql-instances YOUR_PROJECT:us-central1:adcp-sales-agent \
  --set-env-vars "ADCP_AUTH_TEST_MODE=true" \
  --set-env-vars "SUPER_ADMIN_EMAILS=your-email@example.com" \
  --set-env-vars "DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@/salesagent?host=/cloudsql/YOUR_PROJECT:us-central1:adcp-sales-agent"
```

**Important Flags Explained:**
- `--no-cpu-throttling`: Required because the app runs multiple background services (MCP server, Admin UI, A2A server, nginx) that need continuous CPU allocation
- `--min-instances=1`: Keeps at least one instance warm so the services stay running

Note your service URL from the output (e.g., `https://adcp-sales-agent-abc123-uc.a.run.app`).

## Step 4: Verify Deployment

1. Open `https://YOUR-SERVICE-URL.run.app/admin`
2. Click the test login button (in test mode, no OAuth is required)
3. Verify you can access the Admin UI

## Step 5: Configure OAuth (Production)

Once verified, add OAuth for production use.

### Option A: Google OAuth

1. Go to [Google Cloud Console - OAuth credentials](https://console.cloud.google.com/apis/credentials)
2. Click **Create Credentials** > **OAuth client ID**
3. Select **Web application**
4. Add redirect URI: `https://YOUR-SERVICE-URL.run.app/auth/google/callback`

Update your deployment:

```bash
gcloud run services update adcp-sales-agent \
  --region us-central1 \
  --update-env-vars "GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com" \
  --update-env-vars "GOOGLE_CLIENT_SECRET=your-client-secret" \
  --remove-env-vars "ADCP_AUTH_TEST_MODE"
```

### Option B: Other OIDC Providers (Okta, Auth0, Azure AD)

```bash
gcloud run services update adcp-sales-agent \
  --region us-central1 \
  --update-env-vars "OAUTH_CLIENT_ID=your-client-id" \
  --update-env-vars "OAUTH_CLIENT_SECRET=your-client-secret" \
  --update-env-vars "OAUTH_DISCOVERY_URL=https://your-provider/.well-known/openid-configuration" \
  --remove-env-vars "ADCP_AUTH_TEST_MODE"
```

## Step 6: Custom Domain (Optional)

```bash
gcloud beta run domain-mappings create \
  --service adcp-sales-agent \
  --domain sales-agent.yourcompany.com \
  --region us-central1
```

If using a custom domain, add it as an additional redirect URI in your OAuth credentials.

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | Cloud SQL connection string |
| `SUPER_ADMIN_EMAILS` | Yes | Comma-separated admin emails |
| `GEMINI_API_KEY` | No | Platform-level AI key (tenants can configure their own) |
| `GOOGLE_CLIENT_ID` | Prod | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Prod | Google OAuth client secret |
| `ADCP_AUTH_TEST_MODE` | No | Set `true` for initial testing |

## Troubleshooting

### Database connection failed - "No such file or directory"

The DATABASE_URL format should use the Cloud SQL connector:
```
postgresql://user:pass@/dbname?host=/cloudsql/PROJECT:REGION:INSTANCE
```

If you prefer using public IP instead:
1. Get the instance IP: `gcloud sql instances describe adcp-sales-agent --format="value(ipAddresses[0].ipAddress)"`
2. Enable authorized networks: `gcloud sql instances patch adcp-sales-agent --authorized-networks=0.0.0.0/0`
3. Use: `postgresql://user:pass@INSTANCE_IP:5432/dbname`

### Password authentication failed

Special characters in passwords need URL encoding:
- `&` → `%26`
- `=` → `%3D`
- `*` → `%2A`
- `#` → `%23`

### 502 Bad Gateway errors

If you can access `/health` but get 502 errors on `/admin` or `/mcp`, the deployment is missing required flags:
```bash
gcloud run services update adcp-sales-agent \
  --region us-central1 \
  --no-cpu-throttling \
  --min-instances=1
```

The `--no-cpu-throttling` flag is required because the application runs multiple background services that need continuous CPU allocation.

### Redeploy after configuration changes

```bash
gcloud run services update adcp-sales-agent \
  --region us-central1 \
  --update-env-vars "DATABASE_URL=postgresql://..."
```

### View logs

```bash
gcloud run services logs read adcp-sales-agent --region us-central1
```

## Cost Considerations

- **Cloud SQL db-f1-micro**: ~$10/month (can stop when not in use)
- **Cloud Run with --no-cpu-throttling and --min-instances=1**:
  - Always-allocated CPU: ~$30-40/month for 1 vCPU running 24/7
  - Memory (1Gi): Included in CPU cost
  - These settings are required for the application to work correctly
- **Container Registry**: ~$0.10/GB storage

For production, consider upgrading Cloud SQL to a larger tier.

**Note**: Cloud Run's `--no-cpu-throttling` and `--min-instances=1` flags result in higher costs than typical Cloud Run deployments, but are necessary because this application runs multiple background services (MCP server, Admin UI, A2A server, nginx) that require continuous CPU allocation.
