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

### Required Environment Variables

```bash
# API Keys
GEMINI_API_KEY=your-gemini-api-key

# OAuth (choose one method)
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
# OR
GOOGLE_OAUTH_CREDENTIALS_FILE=/path/to/client_secret.json

# Admin Access
SUPER_ADMIN_EMAILS=admin1@example.com,admin2@example.com
SUPER_ADMIN_DOMAINS=example.com

# Database (Docker handles automatically)
DATABASE_URL=postgresql://user:pass@localhost:5432/adcp
```

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

When using Conductor workspaces:

1. Each workspace gets unique ports via `.env`
2. OAuth uses environment variables (not mounted files)
3. Use `docker-compose.override.yml` for dev features
4. Never modify core application files in workspace

## Health Checks

```bash
# MCP Server
curl http://localhost:8080/health

# Admin UI
curl http://localhost:8001/health

# Database
docker exec postgres pg_isready
```
