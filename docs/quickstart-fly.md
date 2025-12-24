# Quickstart: Fly.io

**Time: 10-15 minutes** | **Difficulty: Medium** | **Cost: ~$5-10/month**

Deploy the AdCP Sales Agent to Fly.io with managed PostgreSQL.

## Prerequisites

- [Fly.io account](https://fly.io/app/sign-up) (free tier available)
- [Fly CLI](https://fly.io/docs/hands-on/install-flyctl/) installed
- Credit card on file (required for PostgreSQL, but free tier covers basic usage)

## Steps

### 1. Install and Authenticate Fly CLI (2 min)

```bash
# macOS
brew install flyctl

# Or see https://fly.io/docs/hands-on/install-flyctl/ for other platforms

# Login
fly auth login
```

### 2. Clone the Repository

```bash
git clone https://github.com/adcontextprotocol/salesagent.git
cd salesagent
```

### 3. Create the Application (1 min)

```bash
fly apps create your-app-name
```

Replace `your-app-name` with something unique (e.g., `mycompany-adcp`).

### 4. Create PostgreSQL Database (2-3 min)

```bash
# Create PostgreSQL cluster (this takes 1-2 minutes)
fly postgres create --name your-app-db \
  --region iad \
  --initial-cluster-size 1 \
  --vm-size shared-cpu-1x \
  --volume-size 1

# Attach to your app (auto-sets DATABASE_URL)
fly postgres attach your-app-db --app your-app-name
```

Verify DATABASE_URL was set:
```bash
fly secrets list --app your-app-name
```

### 5. Create Storage Volume (30 sec)

```bash
fly volumes create adcp_data --region iad --size 1 --app your-app-name
```

### 6. Set Required Secrets (1 min)

```bash
# Your email for admin access (REQUIRED)
fly secrets set SUPER_ADMIN_EMAILS="your-email@example.com" --app your-app-name

# Optional: Gemini API key for AI features
fly secrets set GEMINI_API_KEY="your-gemini-key" --app your-app-name
```

### 7. Deploy (3-5 min)

```bash
fly deploy --app your-app-name
```

Watch the logs to ensure it starts correctly:
```bash
fly logs --app your-app-name
```

### 8. Access Your Deployment

Open https://your-app-name.fly.dev/admin

**First login uses test mode** - click the test login button. You can add OAuth later.

## Post-Deployment Setup

### Add Google OAuth (Recommended)

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create OAuth 2.0 Client ID (Web application)
3. Add redirect URI: `https://your-app-name.fly.dev/auth/google/callback`
4. Set secrets:

```bash
fly secrets set GOOGLE_CLIENT_ID="your-client-id.apps.googleusercontent.com" --app your-app-name
fly secrets set GOOGLE_CLIENT_SECRET="your-client-secret" --app your-app-name

# Disable test mode
fly secrets unset ADCP_AUTH_TEST_MODE --app your-app-name
```

### Configure Your Ad Server

1. Log into Admin UI
2. Go to **Settings > Adapters**
3. Configure Google Ad Manager or use Mock adapter for testing

### Custom Domain (Optional)

```bash
fly certs create sales-agent.yourcompany.com --app your-app-name
```

Then add a CNAME record pointing to `your-app-name.fly.dev`.

## Cost Breakdown

| Resource | Cost |
|----------|------|
| App (shared-cpu-1x, 256MB) | ~$2/month |
| PostgreSQL (shared-cpu-1x) | ~$3/month |
| Volume (1GB) | ~$0.15/month |
| **Total** | **~$5-6/month** |

Free tier covers some usage. See [Fly.io Pricing](https://fly.io/docs/about/pricing/).

## Common Commands

```bash
# View logs
fly logs --app your-app-name

# SSH into the machine
fly ssh console --app your-app-name

# Check status
fly status --app your-app-name

# Restart
fly apps restart your-app-name

# Scale up
fly scale vm shared-cpu-2x --app your-app-name
fly scale memory 512 --app your-app-name
```

## Troubleshooting

### Deployment fails

```bash
# Check build logs
fly logs --app your-app-name

# Common fix: ensure DATABASE_URL is attached
fly postgres attach your-app-db --app your-app-name
```

### Database connection error

```bash
# Verify DATABASE_URL exists
fly secrets list --app your-app-name | grep DATABASE

# Re-attach if needed
fly postgres attach your-app-db --app your-app-name
```

### Out of memory

```bash
fly scale memory 512 --app your-app-name
```

### Check database directly

```bash
fly postgres connect --app your-app-db
```

## Next Steps

- **Configure GAM**: See [GAM Adapter Guide](adapters/gam.md)
- **Set up products**: Admin UI > Products
- **Add advertisers**: Admin UI > Advertisers
- **Full documentation**: See [Deployment Guide](deployment.md)
