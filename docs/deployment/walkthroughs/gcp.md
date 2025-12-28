# GCP Cloud Run Deployment

This walkthrough covers deploying the AdCP Sales Agent to Google Cloud Run with Cloud SQL PostgreSQL.

## Prerequisites

1. [Google Cloud Project](https://console.cloud.google.com) with billing enabled
2. [gcloud CLI](https://cloud.google.com/sdk/docs/install) installed and authenticated

## Step 1: Create Cloud SQL PostgreSQL

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

## Step 2: Deploy in Test Mode

Deploy with test mode enabled to verify everything works before configuring OAuth:

```bash
gcloud run deploy adcp-sales-agent \
  --image docker.io/adcontextprotocol/salesagent:latest \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 1Gi \
  --port 8000 \
  --add-cloudsql-instances YOUR_PROJECT:us-central1:adcp-sales-agent \
  --set-env-vars "ADCP_AUTH_TEST_MODE=true" \
  --set-env-vars "SUPER_ADMIN_EMAILS=your-email@example.com" \
  --set-env-vars "DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@/salesagent?host=/cloudsql/YOUR_PROJECT:us-central1:adcp-sales-agent"
```

> **Note**: This uses the prebuilt image from Docker Hub. To build from source instead, run `gcloud builds submit --tag gcr.io/YOUR_PROJECT/adcp-sales-agent` first and use that image.

Note your service URL from the output (e.g., `https://adcp-sales-agent-abc123-uc.a.run.app`).

## Step 3: Verify Deployment

1. Open `https://YOUR-SERVICE-URL.run.app/admin`
2. Click the test login button (in test mode, no OAuth is required)
3. Verify you can access the Admin UI

## Step 4: Configure OAuth (Production)

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

## Step 5: Custom Domain (Optional)

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
| `GOOGLE_CLIENT_ID` | Prod | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Prod | Google OAuth client secret |
| `ADCP_AUTH_TEST_MODE` | No | Set `true` for initial testing |
| `GEMINI_API_KEY` | No | Platform-level AI key (tenants can configure their own) |

## Troubleshooting

### Database connection failed - "No such file or directory"

The DATABASE_URL format is wrong. For Cloud SQL connector, use:
```
postgresql://user:pass@/dbname?host=/cloudsql/PROJECT:REGION:INSTANCE
```

### Password authentication failed

Special characters in passwords need URL encoding:
- `&` → `%26`
- `=` → `%3D`
- `*` → `%2A`
- `#` → `%23`

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
- **Cloud Run**: Pay per use, ~$0 for low traffic
- **Container Registry**: ~$0.10/GB storage

For production, consider upgrading Cloud SQL to a larger tier.
