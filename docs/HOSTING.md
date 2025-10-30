# Hosting Your Own AdCP Sales Agent

This guide covers everything you need to host your own AdCP Sales Agent instance.

## Prerequisites

- Docker installed (for local/container deployment)
- PostgreSQL 15+ database
- Domain name (for production)
- Google OAuth credentials
- (Optional) Google Ad Manager account with OAuth credentials

## Required Environment Variables

### Core Configuration

#### Domain Configuration
```bash
# Your base domain (e.g., scope3.com, yourdomain.com)
BASE_DOMAIN=yourdomain.com

# Sales agent domain (where the agent will be hosted)
SALES_AGENT_DOMAIN=sales-agent.yourdomain.com

# Admin domain (for admin UI)
ADMIN_DOMAIN=admin.sales-agent.yourdomain.com

# Super admin domain (emails from this domain get full access)
SUPER_ADMIN_DOMAIN=yourdomain.com
```

**Default if not set**: Defaults to `scope3.com` for backwards compatibility.

#### Authentication & Authorization
```bash
# Google OAuth (for admin UI login)
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret

# OAuth redirect URI (must match Google OAuth credentials exactly)
GOOGLE_OAUTH_REDIRECT_URI=https://sales-agent.yourdomain.com/admin/auth/google/callback

# Super admin emails (comma-separated)
SUPER_ADMIN_EMAILS=admin@yourdomain.com,admin2@yourdomain.com

# (Optional) Additional super admin domains
SUPER_ADMIN_DOMAINS=yourdomain.com,company.com
```

#### Database
```bash
# Full PostgreSQL connection URL
DATABASE_URL=postgresql://username:password@host:port/database

# Or individual components:
DB_TYPE=postgresql
DB_HOST=localhost
DB_PORT=5432
DB_NAME=adcp
DB_USER=adcp_user
DB_PASSWORD=secure_password
```

#### API Keys
```bash
# Gemini API (for AI features)
GEMINI_API_KEY=your-gemini-api-key

# (Optional) Google Ad Manager OAuth
GAM_OAUTH_CLIENT_ID=your-gam-client-id.apps.googleusercontent.com
GAM_OAUTH_CLIENT_SECRET=your-gam-client-secret

# (Optional) Approximated (for custom domain proxying)
APPROXIMATED_API_KEY=your-approximated-api-key
APPROXIMATED_PROXY_IP=37.16.24.200
APPROXIMATED_BACKEND_URL=sales-agent.yourdomain.com
```

#### GCP Configuration (Optional)
```bash
# Google Cloud Platform project (for service account auto-provisioning)
GCP_PROJECT_ID=your-gcp-project-id

# (Optional) Service account credentials JSON
GOOGLE_APPLICATION_CREDENTIALS_JSON='{"type": "service_account", ...}'
```

#### Production Settings
```bash
# Environment mode
PRODUCTION=true
ENVIRONMENT=production  # or 'development', 'staging'

# Mode flags
ADCP_UNIFIED_MODE=true

# Port configuration (usually not needed - defaults work)
ADCP_SALES_PORT=8080
ADMIN_UI_PORT=8001
A2A_PORT=8091

# Database type
DB_TYPE=postgresql
```

## Deployment Options

### Option 1: Fly.io (Recommended)

1. **Install Fly CLI**:
   ```bash
   curl -L https://fly.io/install.sh | sh
   ```

2. **Login to Fly**:
   ```bash
   fly auth login
   ```

3. **Create app** (first time only):
   ```bash
   fly apps create your-app-name
   ```

4. **Set secrets**:
   ```bash
   # Domain configuration
   fly secrets set BASE_DOMAIN=yourdomain.com --app your-app-name
   fly secrets set SALES_AGENT_DOMAIN=sales-agent.yourdomain.com --app your-app-name
   fly secrets set ADMIN_DOMAIN=admin.sales-agent.yourdomain.com --app your-app-name
   fly secrets set SUPER_ADMIN_DOMAIN=yourdomain.com --app your-app-name

   # Authentication
   fly secrets set GOOGLE_CLIENT_ID=your-client-id --app your-app-name
   fly secrets set GOOGLE_CLIENT_SECRET=your-client-secret --app your-app-name
   fly secrets set GOOGLE_OAUTH_REDIRECT_URI=https://sales-agent.yourdomain.com/admin/auth/google/callback --app your-app-name
   fly secrets set SUPER_ADMIN_EMAILS=admin@yourdomain.com --app your-app-name

   # API Keys
   fly secrets set GEMINI_API_KEY=your-gemini-key --app your-app-name
   fly secrets set GAM_OAUTH_CLIENT_ID=your-gam-id --app your-app-name
   fly secrets set GAM_OAUTH_CLIENT_SECRET=your-gam-secret --app your-app-name

   # GCP (if using service account auto-provisioning)
   fly secrets set GCP_PROJECT_ID=your-gcp-project --app your-app-name

   # Production flags
   fly secrets set PRODUCTION=true --app your-app-name
   fly secrets set ENVIRONMENT=production --app your-app-name
   fly secrets set ADCP_UNIFIED_MODE=true --app your-app-name
   ```

5. **Create PostgreSQL database**:
   ```bash
   fly postgres create --name your-app-db --region iad
   fly postgres attach your-app-db --app your-app-name
   ```

6. **Update fly.toml**:
   - Change `app = "your-app-name"`
   - Update `primary_region` if needed

7. **Deploy**:
   ```bash
   fly deploy --app your-app-name
   ```

8. **Check status**:
   ```bash
   fly status --app your-app-name
   fly logs --app your-app-name
   ```

9. **Configure DNS**:
   - Point your domain to Fly.io app:
   ```bash
   fly ips list --app your-app-name
   ```
   - Add A/AAAA records to your DNS

### Option 2: Docker Compose (Local/Development)

1. **Copy environment file**:
   ```bash
   cp .env.example .env.secrets
   ```

2. **Edit .env.secrets** with your values (see Required Environment Variables above)

3. **Start services**:
   ```bash
   docker-compose up -d
   ```

4. **Check logs**:
   ```bash
   docker-compose logs -f
   ```

5. **Access**:
   - Admin UI: http://localhost:8001
   - MCP Server: http://localhost:8080
   - A2A Server: http://localhost:8091

### Option 3: Kubernetes

1. **Create namespace**:
   ```bash
   kubectl create namespace adcp-sales-agent
   ```

2. **Create secrets**:
   ```bash
   kubectl create secret generic adcp-secrets \
     --from-literal=BASE_DOMAIN=yourdomain.com \
     --from-literal=GOOGLE_CLIENT_ID=your-client-id \
     --from-literal=GOOGLE_CLIENT_SECRET=your-client-secret \
     --from-literal=GEMINI_API_KEY=your-gemini-key \
     --from-literal=DATABASE_URL=postgresql://... \
     -n adcp-sales-agent
   ```

3. **Deploy**:
   ```bash
   kubectl apply -f k8s/ -n adcp-sales-agent
   ```

4. **Expose service**:
   ```bash
   kubectl expose deployment adcp-sales-agent --type=LoadBalancer --port=443 -n adcp-sales-agent
   ```

## Google OAuth Setup

1. **Go to Google Cloud Console** → APIs & Services → Credentials

2. **Create OAuth 2.0 Client ID**:
   - Application type: Web application
   - Name: AdCP Sales Agent
   - Authorized JavaScript origins:
     - `https://sales-agent.yourdomain.com`
     - `http://localhost` (for development)
   - Authorized redirect URIs:
     - `https://sales-agent.yourdomain.com/admin/auth/google/callback`
     - `http://localhost:8001/admin/auth/google/callback` (for development)

3. **Copy credentials**:
   - Client ID → `GOOGLE_CLIENT_ID`
   - Client Secret → `GOOGLE_CLIENT_SECRET`

4. **Configure OAuth consent screen**:
   - User type: Internal (for organization) or External
   - Add scopes: email, profile, openid
   - Add test users (if using External with testing status)

## Google Ad Manager Setup (Optional)

Only needed if using GAM adapter for real ad serving.

1. **Create GAM API credentials** in Google Cloud Console

2. **Set environment variables**:
   ```bash
   GAM_OAUTH_CLIENT_ID=your-gam-client-id
   GAM_OAUTH_CLIENT_SECRET=your-gam-client-secret
   ```

3. **Configure in Admin UI**:
   - Login as super admin
   - Create/edit tenant
   - Go to "Ad Server" settings
   - Select "Google Ad Manager" adapter
   - Follow OAuth flow to authorize

## Database Setup

### First Time Setup

1. **Run migrations**:
   ```bash
   # If using Docker:
   docker-compose exec web python migrate.py

   # If running locally:
   uv run python migrate.py
   ```

2. **Verify database**:
   ```bash
   # Check tables were created
   psql $DATABASE_URL -c "\dt"
   ```

### Creating First Tenant

1. **Login to Admin UI** at https://sales-agent.yourdomain.com/admin

2. **Create tenant**:
   - Click "Create Tenant"
   - Enter organization name and subdomain
   - Configure ad server adapter (Mock for testing, GAM for production)

3. **Create products**:
   - Go to tenant → Products
   - Add advertising products (video ads, display ads, etc.)

4. **Add advertisers**:
   - Go to tenant → Advertisers
   - Create advertiser accounts
   - Get API tokens for each advertiser

## Health Checks & Monitoring

### Health Endpoint
```bash
curl https://sales-agent.yourdomain.com/health
```

Expected response:
```json
{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2025-10-29T18:00:00Z"
}
```

### Monitoring Logs

**Fly.io**:
```bash
fly logs --app your-app-name
```

**Docker**:
```bash
docker-compose logs -f
```

**Kubernetes**:
```bash
kubectl logs -f deployment/adcp-sales-agent -n adcp-sales-agent
```

## Troubleshooting

### OAuth Login Fails

**Issue**: "redirect_uri_mismatch" error

**Fix**:
1. Check `GOOGLE_OAUTH_REDIRECT_URI` matches Google OAuth credentials exactly
2. Ensure redirect URI is added to authorized redirect URIs in Google Console
3. Must include `/admin/auth/google/callback` path

### Database Connection Fails

**Issue**: "connection refused" or "authentication failed"

**Fix**:
1. Verify `DATABASE_URL` is correct
2. Check database is running: `psql $DATABASE_URL -c "SELECT 1"`
3. Ensure database user has proper permissions
4. Run migrations: `python migrate.py`

### Domain Configuration Issues

**Issue**: URLs pointing to wrong domain

**Fix**:
1. Check `BASE_DOMAIN` and `SALES_AGENT_DOMAIN` environment variables
2. Verify DNS is pointing to correct server
3. Clear browser cookies/cache
4. Check `SESSION_COOKIE_DOMAIN` is set correctly (auto-configured from domain vars)

### "No products found" Error

**Issue**: Can't create media buys

**Fix**:
1. Login to Admin UI
2. Go to tenant → Products
3. Create at least one product
4. Ensure product has valid configuration (pricing, formats, etc.)

## Security Considerations

### Required for Production

1. **Use HTTPS**: Always use SSL/TLS certificates for production
2. **Secure secrets**: Use secret management (Fly.io secrets, k8s secrets, env vars)
3. **Restrict super admin**: Limit `SUPER_ADMIN_EMAILS` to trusted users only
4. **Database encryption**: Use encrypted database connections
5. **Strong passwords**: Use strong database passwords
6. **API key rotation**: Rotate API keys regularly

### Never Commit These to Git

- `.env.secrets` - Contains all secrets
- Any file with API keys, passwords, or OAuth credentials
- Database connection strings with credentials

## Scaling

### Vertical Scaling (Fly.io)

```bash
# Increase memory/CPU
fly scale vm shared-cpu-2x --memory 4096 --app your-app-name
```

### Horizontal Scaling

```bash
# Add more instances
fly scale count 3 --app your-app-name
```

### Database Scaling

- Use connection pooling (PgBouncer)
- Enable read replicas for read-heavy workloads
- Consider managed PostgreSQL (Fly Postgres, AWS RDS, etc.)

## Migration from Scope3 Domain

If migrating from existing scope3.com deployment:

1. **Current deployment continues to work** - defaults to scope3.com

2. **To migrate to new domain**:
   ```bash
   fly secrets set BASE_DOMAIN=yourdomain.com --app adcp-sales-agent
   fly secrets set SALES_AGENT_DOMAIN=sales-agent.yourdomain.com --app adcp-sales-agent
   fly secrets set ADMIN_DOMAIN=admin.sales-agent.yourdomain.com --app adcp-sales-agent
   fly secrets set SUPER_ADMIN_DOMAIN=yourdomain.com --app adcp-sales-agent
   ```

3. **Update OAuth credentials** with new redirect URIs

4. **Update DNS** to point to your domain

5. **Deploy** - no code changes needed

## Support & Documentation

- **Main Documentation**: `/docs` directory
- **Architecture**: `/docs/ARCHITECTURE.md`
- **API Documentation**: `/docs/api`
- **Testing Guide**: `/docs/testing`
- **GitHub Issues**: https://github.com/adcontextprotocol/salesagent/issues
