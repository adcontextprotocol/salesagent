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
docker exec postgres pg_isready

# Check connection string
echo $DATABASE_URL
```

#### SQLite vs PostgreSQL Differences
```python
# Problem: PostgreSQL returns tuples
# Solution: Use DictCursor
from psycopg2.extras import DictCursor
conn = psycopg2.connect(..., cursor_factory=DictCursor)

# Problem: Boolean handling
# SQLite: 0/1, PostgreSQL: true/false
# Solution: Use SQLAlchemy Boolean type
```

### UI Issues

#### Page Shows "Loading..." Forever
```javascript
// Check browser console for errors
// Common causes:

// 1. Missing Bootstrap CSS
// Solution: Ensure base.html loads Bootstrap

// 2. API returns HTML instead of JSON
// Solution: Add credentials: 'same-origin' to fetch

// 3. Elements have 0 dimensions
// Solution: Add min-height/width to containers

// 4. JavaScript null errors
// Solution: Use defensive coding
const value = (data?.field || 'default');
```

#### Missing Data in Admin UI
```bash
# Verify tenant_id in session
# Check browser DevTools → Application → Cookies

# Test API directly
curl -H "Cookie: session=YOUR_SESSION" \
  http://localhost:8001/api/tenant/TENANT_ID/products

# Check audit logs for errors
docker exec -it adcp-server python -c \
  "from database_manager import DatabaseManager; \
   db = DatabaseManager(); \
   logs = db.get_audit_logs(limit=10); \
   print(logs)"
```

### Adapter Errors

#### GAM Integration Issues
```python
# Problem: 'DataDownloader' has no attribute 'new_filter_statement'
# Solution: Use StatementBuilder (API changed)
from googleads import ad_manager
statement_builder = ad_manager.StatementBuilder(version='v202411')

# Problem: SUDS objects don't support dict access
# Solution: Serialize first
from zeep.helpers import serialize_object
data = serialize_object(suds_object)
```

#### Dry-Run Not Showing API Calls
```bash
# Enable dry-run mode
python run_simulation.py --dry-run --adapter gam

# Check adapter has dry_run logging
# Look for: if self.dry_run: self.log(...)
```

### Docker Problems

#### Container Won't Start
```bash
# Check logs
docker-compose logs adcp-server

# Common issues:
# - Missing environment variables
# - Port already in use
# - Database not ready

# Clean restart
docker-compose down
docker-compose up -d
```

#### Slow Build Times
```bash
# Use BuildKit caching
export DOCKER_BUILDKIT=1

# Check cache volumes exist
docker volume ls | grep adcp_global

# Clear cache if corrupted
docker volume rm adcp_global_pip_cache
docker volume rm adcp_global_uv_cache
```

### Performance Issues

#### Slow API Responses
```python
# Check database queries
# Enable query logging in PostgreSQL

# Add indexes for common queries
CREATE INDEX idx_media_buys_tenant_status 
ON media_buys(tenant_id, status);

# Use connection pooling
from sqlalchemy.pool import QueuePool
engine = create_engine(url, poolclass=QueuePool)
```

#### High Memory Usage
```bash
# Check container limits
docker stats

# Adjust in docker-compose.yml
deploy:
  resources:
    limits:
      memory: 2G
```

## Error Messages Reference

### Database Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `value too long for type character varying` | Column too short | Increase column length in migration |
| `current transaction is aborted` | Previous error in transaction | Use `db_session.remove()` before operations |
| `'Principal' object has no attribute 'get_adapter_id'` | Wrong import | Import from `schemas`, not `models` |
| `'Tenant' object has no attribute 'config'` | Column removed | Access new normalized columns |

### API Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `401 Unauthorized` | Invalid token | Check x-adcp-auth header |
| `404 Not Found` | Wrong endpoint | Check URL and method |
| `500 Internal Error` | Server error | Check server logs |
| `422 Validation Error` | Invalid request | Check request schema |

## Debug Techniques

### Enable Debug Logging

```bash
# In .env or docker-compose.override.yml
LOG_LEVEL=DEBUG
FLASK_DEBUG=1

# Python logging
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Test Individual Components

```python
# Test database connection
from database_manager import DatabaseManager
db = DatabaseManager()
print(db.engine.url)

# Test adapter
from adapters.mock_ad_server import MockAdapter
adapter = MockAdapter({}, principal)
result = adapter.get_avails(request)

# Test MCP client
from fastmcp.client import Client
client = Client(transport)
result = await client.tools.get_products()
```

### Check System Health

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

1. **Documentation** - Check this guide first
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
- [ ] API returning JSON? Not HTML login page?