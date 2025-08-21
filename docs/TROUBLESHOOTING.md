# Troubleshooting Guide

## Common Issues and Solutions

### Authentication Problems

#### "Access Denied" in Admin UI
```bash
# Check super admin configuration
echo $SUPER_ADMIN_EMAILS
echo $SUPER_ADMIN_DOMAINS

# Verify OAuth credentials
echo $GOOGLE_CLIENT_ID
echo $GOOGLE_CLIENT_SECRET

# Check redirect URI matches exactly
# Must be: http://localhost:8001/auth/google/callback
```

#### Invalid Token for MCP API
```bash
# Get correct token from Admin UI
# Go to Advertisers tab → Copy token

# Or check database
docker exec -it postgres psql -U adcp_user adcp -c \
  "SELECT principal_id, access_token FROM principals;"
```

### Database Issues

#### "Column doesn't exist" Error
```bash
# Run migrations
docker exec -it adcp-server python migrate.py

# Check migration status
docker exec -it adcp-server python migrate.py status

# If migrations fail, check for overlapping revisions
grep -r "revision = " alembic/versions/
```

#### PostgreSQL Connection Failed
```bash
# Check PostgreSQL is running
docker ps | grep postgres

# Test connection
docker exec -it postgres psql -U adcp_user adcp -c "SELECT 1;"

# Check environment variable
echo $DATABASE_URL
```

### Docker Problems

#### Container Won't Start
```bash
# Check logs
docker-compose logs adcp-server
docker-compose logs admin-ui

# Rebuild containers
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Check port conflicts
lsof -i :8080
lsof -i :8001
```

#### Permission Denied Errors
```bash
# Fix volume permissions
docker exec -it adcp-server chown -R $(id -u):$(id -g) /app

# Or run with user ID
docker-compose run --user $(id -u):$(id -g) adcp-server
```

### GAM Integration Issues

#### OAuth Token Invalid
```bash
# Refresh OAuth token
python setup_tenant.py "Publisher" \
  --adapter google_ad_manager \
  --gam-network-code YOUR_CODE \
  --gam-refresh-token NEW_TOKEN

# Verify in database
docker exec -it postgres psql -U adcp_user adcp -c \
  "SELECT gam_refresh_token FROM adapter_configs;"
```

#### Network Code Mismatch
```bash
# Update network code
docker exec -it postgres psql -U adcp_user adcp -c \
  "UPDATE adapter_configs SET gam_network_code='123456' WHERE tenant_id='tenant_id';"
```

### MCP Server Issues

#### "Tool not found" Error
```bash
# List available tools
curl -X POST http://localhost:8080/mcp/ \
  -H "x-adcp-auth: YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"method": "list_tools"}'

# Check tool implementation
grep -r "def get_products" main.py
```

#### SSE Connection Drops
```bash
# Check timeout settings
# In docker-compose.yml, add:
environment:
  - ADCP_REQUEST_TIMEOUT=120
  - ADCP_KEEPALIVE_INTERVAL=30
```

### Admin UI Issues

#### Blank Page or 500 Error
```bash
# Check Flask logs
docker-compose logs admin-ui | grep ERROR

# Enable debug mode
# In docker-compose.override.yml:
environment:
  - FLASK_DEBUG=1
  - FLASK_ENV=development

# Check templates
docker exec -it admin-ui python -c \
  "from admin_ui import app; app.jinja_env.compile('template.html')"
```

#### OAuth Redirect Loop
```bash
# Clear session cookies in browser
# Or use incognito mode

# Verify redirect URI in Google Console
# Must match exactly: http://localhost:8001/auth/google/callback

# Check session secret
echo $FLASK_SECRET_KEY
```

### Performance Issues

#### Slow Database Queries
```bash
# Check query performance
docker exec -it postgres psql -U adcp_user adcp -c \
  "EXPLAIN ANALYZE SELECT * FROM media_buys WHERE tenant_id='test';"

# Add indexes if needed
docker exec -it postgres psql -U adcp_user adcp -c \
  "CREATE INDEX idx_media_buys_tenant ON media_buys(tenant_id);"
```

#### High Memory Usage
```bash
# Check container stats
docker stats

# Limit memory in docker-compose.yml
services:
  adcp-server:
    mem_limit: 512m
    mem_reservation: 256m
```

### API Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `401 Unauthorized` | Invalid token | Check x-adcp-auth header |
| `404 Not Found` | Wrong endpoint | Check URL and method |
| `500 Internal Error` | Server error | Check server logs |
| `422 Validation Error` | Invalid request | Check request schema |
| `400 Invalid ID format` | Malformed IDs | Ensure IDs match pattern |

## Check System Health

```bash
# Service health endpoints
curl http://localhost:8080/health
curl http://localhost:8001/health

# Database health
docker exec postgres pg_isready

# Container health
docker inspect adcp-server | grep Health
```

## Getting Help

### Resources

1. **Documentation** - Check `/docs` directory
2. **GitHub Issues** - Search existing issues
3. **Code Comments** - Read inline documentation
4. **Test Files** - Examples of correct usage

### Reporting Issues

When reporting issues, include:

1. **Error message** - Full stack trace
2. **Environment** - Docker/standalone, OS, versions
3. **Steps to reproduce** - Minimal example
4. **Logs** - Relevant log entries
5. **Configuration** - Sanitized config files

### Quick Fixes Checklist

- [ ] Migrations run? `python migrate.py`
- [ ] Environment variables set? Check `.env`
- [ ] Docker containers running? `docker ps`
- [ ] OAuth configured? Check redirect URI
- [ ] Database accessible? Test connection
- [ ] Logs show errors? `docker-compose logs`
- [ ] Browser console errors? Check DevTools
