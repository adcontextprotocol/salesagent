# Deploying AdCP Sales Agent to Fly.io

This guide covers deploying the AdCP Sales Agent to Fly.io with PostgreSQL database, environment variables, and proper configuration.

## Current Deployment Status

**Successfully deployed** to Fly.io with simplified architecture:
- **URL**: https://adcp-sales-agent.fly.dev
- **Status**: Running (health check passing)
- **Architecture**: Single machine with proxy routing to MCP and Admin UI services

## Prerequisites

1. Install Fly CLI: https://fly.io/docs/hands-on/install-flyctl/
2. Sign up for Fly.io account: https://fly.io/app/sign-up
3. Authenticate: `fly auth login`

## Deployment Steps

### 1. Create Fly App

```bash
# Create the app (one-time setup)
fly apps create adcp-sales-agent --region iad

# Or if app already exists, just set it
fly config app adcp-sales-agent
```

### 2. Set Up PostgreSQL Database

```bash
# Run the setup script
./fly/setup-postgres.sh

# Or manually:
fly postgres create --name adcp-db \
  --region iad \
  --initial-cluster-size 1 \
  --vm-size shared-cpu-1x \
  --volume-size 10

fly postgres attach adcp-db --app adcp-sales-agent
```

### 3. Configure Secrets

First, set up your `.env` file with required values:

```bash
GEMINI_API_KEY=your-gemini-api-key
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
SUPER_ADMIN_EMAILS=admin@example.com
SUPER_ADMIN_DOMAINS=example.com
```

Then run:

```bash
# Source your .env file
source .env

# Run the setup script
./fly/setup-secrets.sh
```

### 4. Create Volume for Persistent Storage

```bash
fly volumes create adcp_data --region iad --size 10
```

### 5. Deploy the Application

```bash
# First deployment
fly deploy

# Subsequent deployments
fly deploy --strategy rolling
```

### 6. Initialize Database (First Time Only)

```bash
# SSH into the running app
fly ssh console

# Run database initialization
cd /app
python init_database.py

# Create initial tenant
python setup_tenant.py "Your Publisher Name" \
  --adapter mock \
  --subdomain yourpublisher

# Exit SSH
exit
```

### 7. Access Your Application

```bash
# Open the application (will redirect to /admin)
fly open

# Direct URLs:
# Admin UI: https://adcp-sales-agent.fly.dev/admin
# MCP Server: https://adcp-sales-agent.fly.dev/mcp/

# View logs
fly logs

# Monitor app
fly status
```

## Configuration Details

### URL Routing

The application uses nginx to route traffic on a single port:

- `/admin`, `/static`, `/auth`, `/api`, `/login`, `/logout` → Admin UI
- `/mcp/` and all other paths → MCP Server  
- `/` → Redirects to `/admin`
- `/health` → Health check endpoint

### Internal Ports

- **8080**: nginx reverse proxy (exposed externally)
- **8080**: MCP Server (internal only)
- **8001**: Admin UI (internal only)

### Environment Variables Set in fly.toml

- `PRODUCTION=true`
- `ADCP_SALES_PORT=8080`
- `ADMIN_UI_PORT=8001`
- `DB_TYPE=postgresql`

### Secrets (set via fly secrets)

- `DATABASE_URL`: Automatically set by Fly when PostgreSQL is attached
- `GEMINI_API_KEY`: Required for AI features
- `GOOGLE_CLIENT_ID`: Required for OAuth
- `GOOGLE_CLIENT_SECRET`: Required for OAuth
- `SUPER_ADMIN_EMAILS`: Comma-separated list of admin emails
- `SUPER_ADMIN_DOMAINS`: Comma-separated list of allowed domains

## Monitoring and Maintenance

### View Logs

```bash
# All logs
fly logs

# Follow logs
fly logs -f

# Logs for specific instance
fly logs -i <instance-id>
```

### SSH Access

```bash
# Connect to app
fly ssh console

# Run commands
cd /app
python manage_tenants.py list
```

### Database Access

```bash
# Connect to PostgreSQL
fly postgres connect -a adcp-db

# Or proxy to local machine
fly proxy 5433:5432 -a adcp-db
# Then connect with: psql postgres://postgres:password@localhost:5433
```

### Scaling

```bash
# Scale instances
fly scale count 2

# Scale VM size
fly scale vm shared-cpu-2x --memory 4096

# Auto-scaling (in fly.toml)
# min_machines_running = 1
# max_machines_running = 5
```

## Troubleshooting

### Check Application Health

```bash
fly status
fly checks list
```

### View Environment

```bash
fly ssh console -C "printenv | grep ADCP"
```

### Database Connection Issues

1. Verify DATABASE_URL is set: `fly secrets list`
2. Check database is running: `fly postgres list`
3. Test connection: `fly postgres connect -a adcp-db`

### OAuth Issues

1. Ensure GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are set
2. Add your Fly.io URLs to Google OAuth authorized redirects:
   - `https://adcp-sales-agent.fly.dev/callback`
   - `https://adcp-sales-agent.fly.dev/auth/callback`

### URL Routing

The application uses nginx reverse proxy with path-based routing:
- Admin UI: `https://adcp-sales-agent.fly.dev/admin`
- MCP Server: `https://adcp-sales-agent.fly.dev/mcp/`
- Static assets: Automatically routed to Admin UI
- Root URL redirects to `/admin`

## Production Considerations

1. **Backups**: Set up regular PostgreSQL backups
   ```bash
   fly postgres backup list -a adcp-db
   ```

2. **Monitoring**: Use Fly's built-in metrics
   ```bash
   fly metrics show
   ```

3. **Secrets Rotation**: Regularly update sensitive secrets
   ```bash
   fly secrets set KEY=new-value
   ```

4. **SSL/TLS**: Automatically handled by Fly.io

5. **Custom Domain**: 
   ```bash
   fly certs create your-domain.com
   ```

## Cost Optimization

- Start with shared-cpu-1x and scale as needed
- Use `auto_stop_machines = "stop"` to save costs during low traffic
- Monitor usage with `fly dashboard`

## Updates and Maintenance

```bash
# Update and redeploy
git pull
fly deploy --strategy rolling

# Run migrations
fly ssh console -C "cd /app && python migrate.py"
```