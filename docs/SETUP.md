# Setup and Configuration Guide

## Installation Methods

### 1. Docker Deployment (Recommended)

```bash
# Start all services
docker-compose up -d

# Services:
# - PostgreSQL database (port 5432)
# - MCP Server (port 8080)
# - Admin UI (port 8001)
```

### 2. Fly.io Deployment

```bash
# Create app and database
fly apps create adcp-sales-agent
fly postgres create --name adcp-db --region iad
fly postgres attach adcp-db --app adcp-sales-agent

# Set secrets
fly secrets set GOOGLE_CLIENT_ID="..." GOOGLE_CLIENT_SECRET="..."
fly secrets set GEMINI_API_KEY="..." SUPER_ADMIN_EMAILS="..."

# Deploy
fly deploy
```

### 3. Standalone Development

```bash
# Install dependencies with uv
uv sync

# Run migrations
uv run python migrate.py

# Start servers
uv run python run_server.py
```

## Configuration

### Environment Setup Options

Choose one of three methods to provide your secrets and configuration:

#### Option 1: `.env.secrets` File (Recommended)

Create `.env.secrets` in the project root directory:

```bash
# Copy template
cp .env.secrets.template .env.secrets

# Edit with your values
# API Keys
GEMINI_API_KEY=your-gemini-api-key

# OAuth Configuration
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
SUPER_ADMIN_EMAILS=admin1@example.com,admin2@example.com
SUPER_ADMIN_DOMAINS=example.com

# GAM OAuth (optional)
GAM_OAUTH_CLIENT_ID=your-gam-client-id.apps.googleusercontent.com
GAM_OAUTH_CLIENT_SECRET=your-gam-client-secret
```

**Benefits**:
- ✅ Consistent across all workspaces/setups
- ✅ Never committed to git (in `.gitignore`)
- ✅ Team-friendly with template

#### Option 2: Shell Environment Variables

Add to your `~/.zshrc` or `~/.bashrc`:

```bash
# AdCP Configuration
export GEMINI_API_KEY="your-gemini-api-key"
export GOOGLE_CLIENT_ID="your-client-id.apps.googleusercontent.com"
export GOOGLE_CLIENT_SECRET="your-client-secret"
export SUPER_ADMIN_EMAILS="admin1@example.com,admin2@example.com"
export GAM_OAUTH_CLIENT_ID="your-gam-client-id.apps.googleusercontent.com"
export GAM_OAUTH_CLIENT_SECRET="your-gam-client-secret"

# Reload shell
source ~/.zshrc
```

#### Option 3: Direct `.env` File

Create `.env` in your working directory:

```bash
# API Keys
GEMINI_API_KEY=your-gemini-api-key
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
SUPER_ADMIN_EMAILS=admin1@example.com,admin2@example.com

# Database (Docker handles automatically)
DATABASE_URL=postgresql://user:pass@localhost:5432/adcp
```

### Priority Order

The setup system checks for configuration in this order:
1. **Current directory**: `.env.secrets` (workspace-specific)
2. **Project root**: `.env.secrets` (shared across workspaces)
3. **Environment variables**: From shell profile
4. **Direct .env**: In current directory

### Google OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create new project or select existing
3. Enable Google+ API
4. Create OAuth 2.0 credentials (Web application)
5. Add redirect URIs:
   - Local: `http://localhost:8001/auth/google/callback`
   - Production: `https://yourdomain.com/auth/google/callback`
6. Download credentials or copy Client ID and Secret

### Database Configuration

#### PostgreSQL (Production)
```bash
DATABASE_URL=postgresql://user:password@host:5432/dbname
DB_TYPE=postgresql
```

#### SQLite (Development)
```bash
DATABASE_URL=sqlite:///adcp_local.db
DB_TYPE=sqlite
```

### Tenant Setup

```bash
# Create publisher/tenant
docker exec -it adcp-server python setup_tenant.py "Publisher Name" \
  --adapter google_ad_manager \
  --gam-network-code 123456

# Create with mock adapter for testing
docker exec -it adcp-server python setup_tenant.py "Test Publisher" \
  --adapter mock
```

## Admin UI Management

The Admin UI provides secure web-based management at http://localhost:8001

### Access Levels

1. **Super Admin** - Full system access
   - Manage all tenants (publishers)
   - View all operations
   - System configuration

2. **Tenant Admin** - Publisher management
   - Manage products and advertisers
   - View tenant operations
   - Configure integrations

3. **Tenant User** - Read-only access
   - View products and campaigns
   - Monitor performance

### Key Features

- **Publisher Management** - Create and configure tenants
- **Advertiser Management** - Add principals (advertisers)
- **Product Catalog** - Define inventory products
- **Creative Approval** - Review and approve creatives
- **Operations Dashboard** - Monitor all activity
- **Audit Logs** - Track all operations

### Publisher Configuration

Each publisher has JSON configuration:

```json
{
  "adapters": {
    "google_ad_manager": {
      "enabled": true,
      "network_code": "123456",
      "manual_approval_required": false
    }
  },
  "creative_engine": {
    "auto_approve_formats": ["display_300x250"],
    "human_review_required": true
  },
  "features": {
    "max_daily_budget": 10000,
    "enable_axe_signals": true
  }
}
```

### Advertiser (Principal) Management

Add advertisers to publishers:

```bash
# Via Admin UI (recommended)
# 1. Login to http://localhost:8001
# 2. Navigate to tenant
# 3. Add new advertiser/principal
# 4. Configure GAM advertiser ID

# Via API
curl -X POST "http://localhost:8001/admin/tenant/{tenant_id}/principals" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Advertiser Name",
    "platform_mappings": {
      "gam_advertiser_id": "123456"
    }
  }'
```

### Product Management

#### AI-Powered Product Creation

Create products with AI assistance:

```bash
# Quick create from templates
curl -X POST "/admin/tenant/{tenant_id}/products/quick-create" \
  -d '{"template": "news_display", "name": "News Display Ads"}'

# Get AI suggestions
curl -X POST "/admin/tenant/{tenant_id}/products/ai-suggest" \
  -d '{"description": "Video ads for sports content"}'
```

#### Default Products

New tenants get 6 standard products:
- Premium Display (guaranteed)
- Standard Display (non-guaranteed)
- Video Pre-Roll (guaranteed)
- Native Content (guaranteed)
- Mobile Display (non-guaranteed)
- Newsletter Sponsorship (guaranteed)

#### Bulk Operations

```bash
# Upload CSV
curl -X POST "/admin/tenant/{tenant_id}/products/upload" \
  -F "file=@products.csv"

# JSON import
curl -X POST "/admin/tenant/{tenant_id}/products/import" \
  -H "Content-Type: application/json" \
  -d @products.json
```

### Creative Management

#### Auto-Approval Workflow

1. Configure auto-approve formats per tenant
2. Standard formats approved instantly
3. Non-standard sent to review queue
4. Admin reviews in UI
5. Email notifications on status change

#### Creative Groups

Organize creatives across campaigns:
- Group by advertiser, campaign, or theme
- Share creatives across media buys
- Track performance by group

## Database Migrations

Migrations run automatically on startup, but can be managed manually:

```bash
# Run migrations
uv run python migrate.py

# Check status
uv run python migrate.py status

# Create new migration
uv run alembic revision -m "description"
```

## Docker Management

### Building and Caching

Docker uses BuildKit caching with shared volumes across Conductor workspaces:
- `adcp_global_pip_cache` - Python packages
- `adcp_global_uv_cache` - uv dependencies

This reduces build times from ~3 minutes to ~30 seconds.

### Common Commands

```bash
# Rebuild after changes
docker-compose build
docker-compose up -d

# View logs
docker-compose logs -f

# Enter container
docker exec -it adcp-server bash

# Backup database
docker exec postgres pg_dump -U adcp_user adcp > backup.sql
```

## Test Authentication Mode

For UI testing without OAuth:

```bash
# Enable in docker-compose.override.yml
ADCP_AUTH_TEST_MODE=true

# Test users available:
# - test_super_admin@example.com / test123
# - test_tenant_admin@example.com / test123
# - test_tenant_user@example.com / test123
```

⚠️ **Never enable in production!**

## Conductor Workspaces

### Quick Setup

For Conductor users, the setup is automated:

```bash
# 1. Create .env.secrets in project root (one-time setup)
cp .env.secrets.template /path/to/project/root/.env.secrets
# Edit with your actual secrets

# 2. Create new Conductor workspace
# Conductor will automatically run setup script

# 3. Start services
docker-compose up -d
```

### How Conductor Setup Works

1. **Automatic Environment Loading**: Setup script finds your `.env.secrets` file
2. **Unique Port Assignment**: Each workspace gets unique ports (no conflicts)
3. **Docker Caching**: Shared cache volumes speed up builds across workspaces
4. **Git Hooks**: Pre-commit and pre-push hooks configured per workspace

### Conductor-Specific Features

- **Port Management**: Automatic port reservation system prevents conflicts
- **Shared Caching**: Docker volumes shared across all AdCP workspaces
- **Workspace Isolation**: Each workspace has independent `.env` with unique ports
- **Development Mode**: Hot reloading with `docker-compose.override.yml`

### Workspace Setup Process

When you create a Conductor workspace, it automatically:

1. **Checks for secrets** in this priority order:
   - `./env.secrets` (workspace-specific)
   - `$CONDUCTOR_ROOT_PATH/.env.secrets` (your main secrets file)
   - Environment variables (your shell profile)

2. **Generates workspace config**:
   - Unique ports (PostgreSQL, MCP Server, Admin UI)
   - Database URL with workspace-specific port
   - Docker caching configuration

3. **Creates development files**:
   - `.env` with secrets + unique ports
   - `docker-compose.override.yml` for hot reloading
   - Git hooks for testing and code quality

4. **Sets up dependencies**:
   - Creates Python virtual environment
   - Installs all dependencies via `uv`
   - Configures UI test dependencies if needed

### Troubleshooting Conductor Setup

**Setup script fails with "missing environment variables":**
```bash
# Create .env.secrets file in project root
cp .env.secrets.template /path/to/project/root/.env.secrets
# Edit with your actual values
```

**Port conflicts:**
```bash
# Check which ports are assigned
cat .env | grep PORT

# Recreate workspace if needed (gets new ports)
```

**Docker caching issues:**
```bash
# Clear shared cache volumes
docker volume rm adcp_global_pip_cache adcp_global_uv_cache

# Restart workspace to recreate volumes
```

**Missing dependencies:**
```bash
# Reinstall in workspace
uv sync --extra ui-tests
```

### Manual Conductor Setup (if automation fails)

```bash
# Set required Conductor variables
export CONDUCTOR_WORKSPACE_NAME="your-workspace"
export CONDUCTOR_WORKSPACE_PATH="/path/to/workspace"
export CONDUCTOR_ROOT_PATH="/path/to/project/root"

# Run setup script manually
bash scripts/setup/setup_conductor_workspace.sh
```

## Health Checks

```bash
# MCP Server
curl http://localhost:8080/health

# Admin UI
curl http://localhost:8001/health

# Database
docker exec postgres pg_isready
```
