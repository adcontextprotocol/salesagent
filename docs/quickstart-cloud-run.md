# Quickstart: Google Cloud Run

**Time: 15-20 minutes** | **Difficulty: Medium-Hard** | **Cost: Pay-per-use**

Deploy the AdCP Sales Agent to Google Cloud Run with Cloud SQL PostgreSQL.

## Why Cloud Run Takes Longer

Unlike platforms with integrated databases, Cloud Run requires separate Cloud SQL setup and network configuration. This guide walks through each step carefully.

## Prerequisites

- [Google Cloud account](https://console.cloud.google.com) with billing enabled
- [gcloud CLI](https://cloud.google.com/sdk/docs/install) installed
- A GCP project (create one at console.cloud.google.com)

## Steps

### 1. Set Up gcloud CLI (2 min)

```bash
# Install (macOS)
brew install --cask google-cloud-sdk

# Or see https://cloud.google.com/sdk/docs/install

# Login and set project
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

### 2. Enable Required APIs (1 min)

```bash
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  sqladmin.googleapis.com
```

### 3. Create Cloud SQL Instance (3-5 min)

This is the longest step - Cloud SQL instances take a few minutes to provision.

```bash
# Create PostgreSQL instance (cheapest tier)
gcloud sql instances create adcp-sales-agent \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=us-central1 \
  --root-password=CHOOSE_A_STRONG_PASSWORD
```

**Save your password** - you'll need it for DATABASE_URL.

Wait for the instance to be ready:
```bash
gcloud sql instances describe adcp-sales-agent --format="value(state)"
# Should show "RUNNABLE"
```

### 4. Get Connection Details (1 min)

```bash
# Get the public IP
gcloud sql instances describe adcp-sales-agent \
  --format="value(ipAddresses[0].ipAddress)"

# Get the connection name
gcloud sql instances describe adcp-sales-agent \
  --format="value(connectionName)"
```

Note both values. Example:
- **Public IP**: `34.46.58.47`
- **Connection name**: `your-project:us-central1:adcp-sales-agent`

### 5. Configure Network Access (1 min)

For initial testing, allow all IPs (restrict this in production):

```bash
gcloud sql instances patch adcp-sales-agent \
  --authorized-networks=0.0.0.0/0
```

**Production note**: Use Cloud SQL Auth Proxy or VPC instead of public access.

### 6. Build and Push Docker Image (2-3 min)

```bash
# Clone the repo
git clone https://github.com/adcontextprotocol/salesagent.git
cd salesagent

# Build and push to Google Container Registry
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/adcp-sales-agent
```

### 7. Prepare Your DATABASE_URL

Format: `postgresql://USER:PASSWORD@IP:5432/postgres`

**Important**: URL-encode special characters in your password:
- `&` → `%26`
- `=` → `%3D`
- `*` → `%2A`
- `#` → `%23`
- `@` → `%40`

Example: If password is `My&Pass=123`, use `My%26Pass%3D123`

Your DATABASE_URL should look like:
```
postgresql://postgres:YOUR_ENCODED_PASSWORD@34.46.58.47:5432/postgres
```

### 8. Deploy to Cloud Run (2 min)

```bash
gcloud run deploy adcp-sales-agent \
  --image gcr.io/YOUR_PROJECT_ID/adcp-sales-agent \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 1Gi \
  --port 8000 \
  --set-env-vars="DATABASE_URL=postgresql://postgres:YOUR_ENCODED_PASSWORD@YOUR_IP:5432/postgres" \
  --set-env-vars="SUPER_ADMIN_EMAILS=your-email@example.com" \
  --set-env-vars="ADCP_AUTH_TEST_MODE=true"
```

Note the service URL from the output (e.g., `https://adcp-sales-agent-abc123-uc.a.run.app`).

### 9. Verify Deployment

```bash
curl https://YOUR_SERVICE_URL/health
```

Should return `{"status": "healthy"}`.

### 10. Access Admin UI

Open `https://YOUR_SERVICE_URL/admin`

Click the test login button (test mode is enabled).

## Post-Deployment Setup

### Add Google OAuth (Recommended)

1. Go to [Google Cloud Console Credentials](https://console.cloud.google.com/apis/credentials)
2. Create OAuth 2.0 Client ID (Web application)
3. Add redirect URI: `https://YOUR_SERVICE_URL/auth/google/callback`
4. Update deployment:

```bash
gcloud run services update adcp-sales-agent \
  --region us-central1 \
  --update-env-vars="GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com" \
  --update-env-vars="GOOGLE_CLIENT_SECRET=your-client-secret" \
  --remove-env-vars="ADCP_AUTH_TEST_MODE"
```

### Add Gemini API Key (Optional)

```bash
gcloud run services update adcp-sales-agent \
  --region us-central1 \
  --update-env-vars="GEMINI_API_KEY=your-gemini-key"
```

### Use Cloud SQL Connector (More Secure)

Instead of public IP, use the Cloud SQL socket connection:

```bash
gcloud run services update adcp-sales-agent \
  --region us-central1 \
  --add-cloudsql-instances=YOUR_PROJECT:us-central1:adcp-sales-agent \
  --update-env-vars="DATABASE_URL=postgresql://postgres:YOUR_ENCODED_PASSWORD@/postgres?host=/cloudsql/YOUR_PROJECT:us-central1:adcp-sales-agent"
```

Then remove public access from Cloud SQL:
```bash
gcloud sql instances patch adcp-sales-agent --clear-authorized-networks
```

## Troubleshooting

### "No such file or directory" database error

Your DATABASE_URL is missing the host. Use format:
```
postgresql://postgres:password@IP_ADDRESS:5432/postgres
```

### "Connection refused" error

Cloud SQL authorized networks not configured:
```bash
gcloud sql instances patch adcp-sales-agent \
  --authorized-networks=0.0.0.0/0
```

### "Password authentication failed"

Special characters need URL encoding. Test your password:
```bash
# Python helper
python3 -c "import urllib.parse; print(urllib.parse.quote('YOUR_PASSWORD', safe=''))"
```

### Container keeps restarting

Check logs:
```bash
gcloud run services logs read adcp-sales-agent --region us-central1 --limit 50
```

### Redeploy after fixing issues

```bash
gcloud run services update adcp-sales-agent \
  --region us-central1 \
  --update-env-vars="DATABASE_URL=postgresql://..."
```

## Cost Estimate

| Resource | Cost |
|----------|------|
| Cloud Run | Pay-per-request (~$0-5/month for low traffic) |
| Cloud SQL (db-f1-micro) | ~$7-10/month |
| Container Registry | ~$0.10/GB/month |
| **Total** | **~$8-15/month** |

See [Cloud Run Pricing](https://cloud.google.com/run/pricing) and [Cloud SQL Pricing](https://cloud.google.com/sql/pricing).

## Alternative: Cloud Run Button

The "Run on Google Cloud" button in the README uses this same process but with a web UI. It still requires:
1. Pre-existing Cloud SQL instance
2. Manual network configuration
3. Correct DATABASE_URL format

The button doesn't automate Cloud SQL setup - you'll still need to follow steps 3-5 above first.

## Next Steps

- **Configure GAM**: See [GAM Adapter Guide](adapters/gam.md)
- **Custom domain**: `gcloud beta run domain-mappings create --service adcp-sales-agent --domain your-domain.com`
- **Full documentation**: See [Deployment Guide](deployment.md)
