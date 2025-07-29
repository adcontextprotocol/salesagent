# Docker Deployment Guide

## Quick Start with Docker Compose

The easiest way to deploy AdCP Sales Agent with PostgreSQL:

```bash
# Clone the repository
git clone https://github.com/your-org/adcp-buy-server.git
cd adcp-buy-server

# Copy environment example
cp .env.example .env

# Edit .env and add your Gemini API key
# GEMINI_API_KEY=your-actual-key-here

# Start services
docker-compose up -d

# View logs
docker-compose logs -f

# Server will be available at http://localhost:8080
```

## Production Deployment

### 1. Using Docker Compose (Recommended)

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: adcp
      POSTGRES_USER: adcp_user
      POSTGRES_PASSWORD: ${DB_PASSWORD}  # Set in .env
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

  adcp-server:
    image: adcp-buy-server:latest
    environment:
      DATABASE_URL: postgresql://adcp_user:${DB_PASSWORD}@postgres:5432/adcp
      GEMINI_API_KEY: ${GEMINI_API_KEY}
      ADCP_SALES_PORT: 8080
      ADMIN_UI_PORT: 8001
    depends_on:
      - postgres
    ports:
      - "8080:8080"  # MCP Server
      - "8001:8001"  # Admin UI
    volumes:
      - ./audit_logs:/app/audit_logs
    restart: unless-stopped

volumes:
  postgres_data:
```

### 2. Building the Docker Image

```bash
# Build with Docker
docker build -t adcp-buy-server:latest .

# Or with specific platform
docker buildx build --platform linux/amd64 -t adcp-buy-server:latest .
```

### 3. Running Standalone Container

```bash
# With external PostgreSQL
docker run -d \
  --name adcp-server \
  -p 8080:8080 \
  -e DATABASE_URL=postgresql://user:pass@db-host:5432/adcp \
  -e GEMINI_API_KEY=your-key \
  -v $(pwd)/audit_logs:/app/audit_logs \
  adcp-buy-server:latest

# With SQLite (persistent volume)
docker run -d \
  --name adcp-server \
  -p 8080:8080 \
  -e GEMINI_API_KEY=your-key \
  -v adcp-data:/root/.adcp \
  -v $(pwd)/audit_logs:/app/audit_logs \
  adcp-buy-server:latest
```

## Configuration Options

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | Full database connection URL | Uses SQLite |
| `DB_TYPE` | Database type: `sqlite` or `postgresql` | `sqlite` |
| `DB_HOST` | PostgreSQL host | `localhost` |
| `DB_PORT` | PostgreSQL port | `5432` |
| `DB_NAME` | Database name | `adcp` |
| `DB_USER` | Database user | `adcp` |
| `DB_PASSWORD` | Database password | - |
| `GEMINI_API_KEY` | Google Gemini API key (required) | - |
| `ADCP_DRY_RUN` | Enable dry-run mode | `false` |
| `DATA_DIR` | SQLite data directory | `~/.adcp` |
| `ADCP_SALES_PORT` | MCP server port | `8080` |
| `ADMIN_UI_PORT` | Admin UI port | `8001` |
| `SUPER_ADMIN_EMAILS` | Comma-separated super admin emails | - |
| `SUPER_ADMIN_DOMAINS` | Comma-separated admin domains | - |

### Volumes

| Path | Description |
|------|-------------|
| `/app/audit_logs` | Audit log files |
| `/root/.adcp` | SQLite database (if using SQLite) |

## Multi-Tenant Setup

After starting the container, create tenants:

```bash
# Enter the container
docker exec -it adcp-server bash

# Create a new tenant
python setup_tenant.py "Publisher Name" \
  --adapter google_ad_manager \
  --gam-network-code 123456

# Exit container
exit
```

## Scaling Considerations

### With PostgreSQL

PostgreSQL allows multiple server instances:

```yaml
services:
  adcp-server:
    image: adcp-buy-server:latest
    deploy:
      replicas: 3
    environment:
      DATABASE_URL: postgresql://user:pass@postgres:5432/adcp
```

### Load Balancing

Add a load balancer for multiple instances:

```yaml
services:
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - adcp-server
```

## Monitoring

### Health Checks

The container includes health checks:

```bash
# Check health
curl http://localhost:8080/health

# Check specific container
docker inspect adcp-server --format='{{.State.Health.Status}}'
```

### Logs

```bash
# View logs
docker-compose logs -f adcp-server

# View audit logs
docker exec adcp-server ls -la /app/audit_logs
```

## Backup and Restore

### PostgreSQL Backup

```bash
# Backup
docker-compose exec postgres pg_dump -U adcp_user adcp > backup.sql

# Restore
docker-compose exec -T postgres psql -U adcp_user adcp < backup.sql
```

### SQLite Backup

```bash
# Backup
docker cp adcp-server:/root/.adcp/adcp.db ./backup.db

# Restore
docker cp ./backup.db adcp-server:/root/.adcp/adcp.db
```

## Security Best Practices

1. **Use Secrets**: Store sensitive data in Docker secrets or environment files
2. **Network Isolation**: Use custom networks for service communication
3. **Non-Root User**: Container runs as non-root user `adcp`
4. **Volume Permissions**: Ensure proper permissions on mounted volumes
5. **SSL/TLS**: Use a reverse proxy with SSL certificates

### Example with Traefik

```yaml
services:
  traefik:
    image: traefik:v2.10
    command:
      - "--providers.docker=true"
      - "--entrypoints.websecure.address=:443"
    ports:
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./certs:/certs

  adcp-server:
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.adcp.rule=Host(`adcp.example.com`)"
      - "traefik.http.routers.adcp.entrypoints=websecure"
      - "traefik.http.routers.adcp.tls=true"
```

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker logs adcp-server

# Common issues:
# - Missing GEMINI_API_KEY
# - Database connection failed
# - Port already in use
```

### Database Connection Issues

```bash
# Test PostgreSQL connection
docker-compose exec adcp-server python -c "
from db_config import get_db_connection
conn = get_db_connection()
print('Connected successfully!')
"
```

### Permission Errors

```bash
# Fix audit log permissions
docker exec adcp-server chown -R adcp:adcp /app/audit_logs
```

## Example Production Setup

Complete production-ready `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: adcp
      POSTGRES_USER: adcp_user
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    secrets:
      - db_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - backend
    restart: unless-stopped

  adcp-server:
    image: adcp-buy-server:latest
    environment:
      DATABASE_URL: postgresql://adcp_user:${DB_PASSWORD}@postgres:5432/adcp?sslmode=require
      GEMINI_API_KEY_FILE: /run/secrets/gemini_key
    secrets:
      - db_password
      - gemini_key
    depends_on:
      - postgres
    networks:
      - backend
      - frontend
    volumes:
      - ./audit_logs:/app/audit_logs:rw
    restart: unless-stopped
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: '1'
          memory: 1G

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./certs:/etc/nginx/certs:ro
    networks:
      - frontend
    restart: unless-stopped

networks:
  backend:
    driver: bridge
  frontend:
    driver: bridge

volumes:
  postgres_data:

secrets:
  db_password:
    file: ./secrets/db_password.txt
  gemini_key:
    file: ./secrets/gemini_key.txt
```

This provides a complete, production-ready Docker setup with PostgreSQL!