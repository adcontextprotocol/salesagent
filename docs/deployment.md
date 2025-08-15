# Deployment Guide

## Overview

The AdCP Sales Agent can be deployed in multiple ways:
- **Docker Compose** (recommended for most deployments)
- **Fly.io** (managed cloud deployment)
- **Standalone** (development only)

## Docker Deployment (Recommended)

### Prerequisites
- Docker and Docker Compose installed
- Environment variables configured
- Google OAuth credentials (for Admin UI)

### Quick Start

1. **Clone and configure:**
   ```bash
   git clone https://github.com/adcontextprotocol/salesagent.git
   cd salesagent
   cp .env.example .env
   # Edit .env with your configuration
   ```

2. **Start services:**
   ```bash
   docker-compose up -d
   ```

3. **Initialize database:**
   ```bash
   docker exec -it adcp-buy-server-adcp-server-1 python migrate.py
   docker exec -it adcp-buy-server-adcp-server-1 python init_database.py
   ```

4. **Access services:**
   - MCP Server: http://localhost:8080/mcp/
   - Admin UI: http://localhost:8001
   - PostgreSQL: localhost:5432

### Docker Services

The `docker-compose.yml` defines three services:

```yaml
services:
  postgres:      # PostgreSQL database
  adcp-server:   # MCP server (port 8080)  
  admin-ui:      # Admin interface (port 8001)
```

### Docker Caching

The system uses BuildKit caching with shared volumes:
- `adcp_global_pip_cache` - Python packages cache
- `adcp_global_uv_cache` - uv dependencies cache

This reduces rebuild times from ~3 minutes to ~30 seconds across all Conductor workspaces.

### Docker Management

```bash
# Rebuild after code changes
docker-compose build
docker-compose up -d

# View logs
docker-compose logs -f
docker-compose logs -f adcp-server

# Stop services
docker-compose down

# Reset everything (including volumes)
docker-compose down -v

# Enter container
docker exec -it adcp-buy-server-adcp-server-1 bash

# Backup database
docker exec adcp-buy-server-postgres-1 \
  pg_dump -U adcp_user adcp > backup.sql
```

## Fly.io Deployment

### Overview

Deploy to Fly.io for a managed cloud solution with automatic SSL, global distribution, and integrated PostgreSQL.

### Architecture

```
Internet → Fly.io Edge → Proxy (8000) → MCP Server (8080)
                                      → Admin UI (8001)
```

### Prerequisites

1. **Install Fly CLI:**
   ```bash
   brew install flyctl  # macOS
   # or see https://fly.io/docs/hands-on/install-flyctl/
   ```

2. **Authenticate:**
   ```bash
   fly auth login
   ```

### Deployment Steps

1. **Create application:**
   ```bash
   fly apps create adcp-sales-agent
   ```

2. **Create PostgreSQL cluster:**
   ```bash
   fly postgres create --name adcp-db \
     --region iad \
     --initial-cluster-size 1 \
     --vm-size shared-cpu-1x \
     --volume-size 10
   
   fly postgres attach adcp-db --app adcp-sales-agent
   ```

3. **Create persistent volume:**
   ```bash
   fly volumes create adcp_data --region iad --size 1
   ```

4. **Set secrets:**
   ```bash
   # OAuth configuration
   fly secrets set GOOGLE_CLIENT_ID="your-client-id.apps.googleusercontent.com"
   fly secrets set GOOGLE_CLIENT_SECRET="your-client-secret"
   
   # Admin configuration
   fly secrets set SUPER_ADMIN_EMAILS="admin@example.com"
   fly secrets set SUPER_ADMIN_DOMAINS="example.com"
   
   # API keys
   fly secrets set GEMINI_API_KEY="your-gemini-api-key"
   ```

5. **Configure OAuth redirect URI:**
   
   Add to Google Cloud Console:
   ```
   https://adcp-sales-agent.fly.dev/auth/google/callback
   ```

6. **Deploy:**
   ```bash
   fly deploy
   ```

7. **Initialize database (first time only):**
   ```bash
   fly ssh console -C "cd /app && python init_database.py"
   ```

### Fly.io Configuration Files

- `fly.toml` - Main application configuration
- `Dockerfile.fly` - Optimized Docker image for Fly.io
- `fly-proxy.py` - Request routing proxy
- `debug_start.sh` - Service startup script

### Monitoring on Fly.io

```bash
# View logs
fly logs

# Check status
fly status

# SSH into machine
fly ssh console

# View metrics
fly dashboard

# Scale horizontally
fly scale count 2

# Scale vertically  
fly scale vm shared-cpu-2x
```

### Accessing Services

- Admin UI: https://adcp-sales-agent.fly.dev/admin
- MCP Endpoint: https://adcp-sales-agent.fly.dev/mcp/
- Health Check: https://adcp-sales-agent.fly.dev/health

## Environment Configuration

### Required Variables

```bash
# API Keys
GEMINI_API_KEY=your-gemini-api-key-here

# OAuth Configuration (choose one method)
# Method 1: Environment variables (recommended)
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret

# Method 2: File path (legacy)
# GOOGLE_OAUTH_CREDENTIALS_FILE=/path/to/client_secret.json

# Admin Configuration
SUPER_ADMIN_EMAILS=user1@example.com,user2@example.com
SUPER_ADMIN_DOMAINS=example.com

# Database (Docker/Fly.io handle automatically)
DATABASE_URL=postgresql://user:pass@host:5432/dbname
```

### Google OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create new project or select existing
3. Enable Google+ API
4. Create OAuth 2.0 Client ID (Web application)
5. Add authorized redirect URIs:
   - Local: `http://localhost:8001/auth/google/callback`
   - Docker: `http://localhost:8001/auth/google/callback`
   - Fly.io: `https://your-app.fly.dev/auth/google/callback`
   - Conductor: `http://localhost:8002-8011/auth/google/callback`
6. Download credentials or copy Client ID and Secret

### Database Configuration

#### PostgreSQL (Production)
```bash
DATABASE_URL=postgresql://user:password@host:5432/dbname
DB_TYPE=postgresql
```

#### SQLite (Development Only)
```bash
DATABASE_URL=sqlite:///adcp_local.db
DB_TYPE=sqlite
```

## Tenant Management

### Creating Tenants

```bash
# Docker deployment
docker exec -it adcp-buy-server-adcp-server-1 python setup_tenant.py \
  "Publisher Name" \
  --adapter google_ad_manager \
  --gam-network-code 123456 \
  --gam-refresh-token YOUR_REFRESH_TOKEN

# Fly.io deployment
fly ssh console -C "python setup_tenant.py 'Publisher Name' \
  --adapter google_ad_manager \
  --gam-network-code 123456"

# Mock adapter for testing
python setup_tenant.py "Test Publisher" --adapter mock
```

### Managing Principals (Advertisers)

After creating a tenant:
1. Login to Admin UI with Google OAuth
2. Navigate to "Advertisers" tab
3. Click "Add Advertiser"
4. Each advertiser gets their own API token

## Database Migrations

### Automatic Migrations

Migrations run automatically on startup via `entrypoint.sh`.

### Manual Migration Management

```bash
# Run migrations
uv run python migrate.py

# Check migration status
uv run python migrate.py status

# Create new migration
uv run alembic revision -m "description_of_change"

# Rollback last migration
uv run alembic downgrade -1
```

### Migration Best Practices

1. Always test on both SQLite and PostgreSQL
2. Use SQLAlchemy operations for compatibility
3. Include proper downgrade logic
4. Test with fresh database before deploying

## Health Monitoring

### Health Check Endpoints

```bash
# MCP Server health
curl http://localhost:8080/health

# Admin UI health
curl http://localhost:8001/health

# PostgreSQL health (Docker)
docker exec adcp-buy-server-postgres-1 pg_isready
```

### Monitoring Metrics

The system prepares for Prometheus metrics:
- Request latency
- Active media buys
- API call rates
- Error rates

## Security Considerations

### Production Checklist

- [ ] Use HTTPS everywhere (automatic on Fly.io)
- [ ] Set strong database passwords
- [ ] Rotate API keys regularly
- [ ] Enable audit logging
- [ ] Configure rate limiting
- [ ] Use environment variables for secrets
- [ ] Never commit `.env` files
- [ ] Implement backup strategy
- [ ] Monitor error logs
- [ ] Set up alerting

### SSL/TLS Configuration

#### Fly.io
SSL is automatic - Fly.io handles certificates.

#### Docker with Nginx
```nginx
server {
    listen 443 ssl;
    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    
    location / {
        proxy_pass http://admin-ui:8001;
    }
    
    location /mcp/ {
        proxy_pass http://adcp-server:8080;
    }
}
```

## Backup and Recovery

### Database Backup

#### PostgreSQL Backup
```bash
# Docker
docker exec adcp-buy-server-postgres-1 \
  pg_dump -U adcp_user adcp > backup_$(date +%Y%m%d).sql

# Fly.io
fly postgres backup create --app adcp-db
```

#### PostgreSQL Restore
```bash
# Docker
docker exec -i adcp-buy-server-postgres-1 \
  psql -U adcp_user adcp < backup.sql

# Fly.io
fly postgres backup restore <backup-id> --app adcp-db
```

### File Backup

Important files to backup:
- `.env` configuration
- `conductor_ports.json` (if using Conductor)
- Database backups
- Custom adapter configurations

## Troubleshooting Deployment

### Common Issues

#### Port Conflicts
```bash
# Check what's using a port
lsof -i :8080

# Kill process using port
kill -9 $(lsof -t -i:8080)
```

#### Database Connection Issues
```bash
# Test connection
psql postgresql://user:pass@localhost:5432/adcp

# Check Docker network
docker network ls
docker network inspect salesagent_default
```

#### OAuth Redirect Mismatch
- Ensure redirect URI matches exactly (including trailing slash)
- Check for http vs https
- Verify port numbers match

#### Container Won't Start
```bash
# Check logs
docker-compose logs adcp-server

# Rebuild from scratch
docker-compose down -v
docker-compose build --no-cache
docker-compose up
```

### Debug Mode

Enable debug logging:
```bash
# Docker
DEBUG=true docker-compose up

# Fly.io
fly secrets set DEBUG=true
```

## Migration from Single-Tenant

If migrating from an older single-tenant version:

1. **Backup existing data:**
   ```bash
   cp adcp.db adcp_backup.db
   sqlite3 adcp.db .dump > backup.sql
   ```

2. **Update code:**
   ```bash
   git pull
   uv sync
   ```

3. **Run migration:**
   ```bash
   uv run python migrate.py
   ```

The system will automatically:
- Create a default tenant from existing config
- Migrate data to multi-tenant schema
- Generate authentication tokens

## Performance Tuning

### PostgreSQL Optimization

```sql
-- Increase connections
ALTER SYSTEM SET max_connections = 200;

-- Optimize for SSD
ALTER SYSTEM SET random_page_cost = 1.1;

-- Increase shared buffers
ALTER SYSTEM SET shared_buffers = '256MB';
```

### Docker Resource Limits

```yaml
services:
  adcp-server:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

### Connection Pooling

The system uses SQLAlchemy connection pooling:
```python
# Configured in database.py
pool_size=20
max_overflow=40
pool_timeout=30
```

## Scaling Strategies

### Horizontal Scaling

#### Docker Swarm
```bash
docker swarm init
docker stack deploy -c docker-compose.yml adcp
docker service scale adcp_adcp-server=3
```

#### Fly.io
```bash
fly scale count 3 --region iad
fly scale count 2 --region lhr
```

### Vertical Scaling

#### Docker
Update `docker-compose.yml` resource limits.

#### Fly.io
```bash
fly scale vm dedicated-cpu-2x
fly scale memory 4096
```

## Maintenance Mode

To enable maintenance mode:

1. **Create maintenance page:**
   ```html
   <!-- templates/maintenance.html -->
   <h1>System Maintenance</h1>
   <p>We'll be back shortly.</p>
   ```

2. **Enable in Admin UI:**
   ```python
   # Set environment variable
   MAINTENANCE_MODE=true
   ```

3. **Or use nginx:**
   ```nginx
   location / {
       if (-f /var/www/maintenance.html) {
           return 503;
       }
       proxy_pass http://upstream;
   }
   error_page 503 /maintenance.html;
   ```