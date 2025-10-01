# Troubleshooting Guide

## Production Emergency Response

### Critical Production Failures

#### Database Schema Conflicts
**Symptoms**: `operator does not exist: text < timestamp with time zone`
- **Immediate Action**: Identify which queries are failing
- **Root Cause**: Schema type mismatches between expected and actual column types
- **Emergency Fix**: Comment out problematic queries temporarily
- **Permanent Fix**: Migrate to consistent schema or eliminate conflicting systems

#### Broken Migration Chain
**Symptoms**: `Can't locate revision identified by '[revision_id]'`
- **Immediate Diagnosis**: `alembic history` to check chain integrity
- **Emergency Repair**:
  1. Identify last known good revision: `alembic current`
  2. Reset to good revision: `alembic stamp [good_revision]`
  3. Create new migration with correct `down_revision`
  4. Test locally before deploying
- **Deploy**: Migration fix first, then code changes

#### Application Crash Loops
**Symptoms**: App repeatedly crashes on startup, "smoke checks failed"
- **Immediate Response**: Check `fly logs --app adcp-sales-agent`
- **Debug Process**:
  1. Identify specific error in logs
  2. Check recent PR changes: `git log --oneline -10`
  3. Test fix locally with Docker
  4. Deploy minimal fix to restore service
  5. Implement broader changes incrementally

#### Emergency Recovery Steps
```bash
# 1. Check current production status
fly status --app adcp-sales-agent

# 2. Review recent logs for errors
fly logs --app adcp-sales-agent --limit 100

# 3. Check deployment history
fly releases --app adcp-sales-agent

# 4. Rollback if needed (last resort)
fly releases rollback --app adcp-sales-agent [release_id]

# 5. Deploy emergency fix
fly deploy --app adcp-sales-agent
```

## Common Issues and Solutions

### Dashboard and UI Issues

#### "Error loading dashboard" (HISTORICAL - FIXED)
This was caused by the dashboard querying deprecated `Task` models.

**Historical Issue**: Dashboard was querying `tasks` table that had schema conflicts.
**Resolution**: Dashboard now uses `WorkflowStep` model for activity tracking.
**Current State**: No task-related queries - dashboard shows workflow activity.

#### Task-related errors (HISTORICAL - FIXED)
These errors are resolved by the workflow system migration.

**Historical Issue**: Missing task management templates and deprecated task models.
**Resolution**: Task system eliminated in favor of unified workflow system.
**Current State**: Dashboard shows workflow activity feed instead of task lists.

#### Activity Feed Not Updating
The activity feed uses Server-Sent Events (SSE) for real-time updates.

**Check:**
1. SSE endpoint is accessible: `http://localhost:8001/admin/tenant/{tenant_id}/events`
2. Database audit_logs table is being populated
3. No browser extensions blocking SSE connections

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

#### MCP Returns Empty Products Array
```bash
# Check if products exist for the tenant
docker exec -it postgres psql -U adcp_user adcp -c \
  "SELECT COUNT(*) FROM products WHERE tenant_id='your_tenant_id';"

# Create products using Admin UI or database script
# Products are tenant-specific and must be created for each tenant
```

#### "Missing or invalid x-adcp-auth header" with Valid Token
```bash
# Verify tenant is active
docker exec -it postgres psql -U adcp_user adcp -c \
  "SELECT is_active FROM tenants WHERE tenant_id='your_tenant_id';"

# Check if using SSE transport (may not forward headers properly)
# Use direct HTTP requests for debugging instead of SSE
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

#### Contract Validation Errors (Prevention System Available)
**Symptoms**: `Input validation error: 'brief' is a required property` or similar parameter validation failures

**Immediate Diagnosis**:
```bash
# Test the specific failing request
uv run python -c "
from src.core.schemas import GetProductsRequest
try:
    req = GetProductsRequest(promoted_offering='test product')
    print('✅ Request creation successful')
except Exception as e:
    print(f'❌ Validation error: {e}')
"

# Run contract validation tests
uv run pytest tests/integration/test_mcp_contract_validation.py -v

# Audit all schema requirements
uv run python scripts/audit_required_fields.py
```

**Common Fixes**:
- Make over-strict fields optional with sensible defaults
- Update MCP tool parameter ordering (required first, optional with defaults)
- Add contract validation tests for new schemas

**Prevention**:
- Use pre-commit hooks: `pre-commit run mcp-contract-validation --all-files`
- Test minimal parameter creation for all Request models
- Follow schema design guidelines in CLAUDE.md

### A2A Protocol Issues

#### JSON-RPC "Invalid messageId" Error
```bash
# A2A spec requires string messageId, not numeric
# Old format (incorrect):
{"id": 123, "params": {"message": {"messageId": 456}}}

# New format (correct):
{"id": "123", "params": {"message": {"messageId": "456"}}}

# Server has backward compatibility middleware
# but clients should update to use strings
```

#### A2A Server Not Responding
```bash
# Check if A2A server is running
docker ps | grep a2a

# Test A2A endpoint directly
curl http://localhost:8091/.well-known/agent.json

# Check logs for errors
docker logs adcp-server | grep a2a
```

#### A2A Authentication Failed
```bash
# Use Bearer token in Authorization header
curl -X POST http://localhost:8091/a2a \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "message/send", ...}'

# Avoid deprecated query parameter auth
# Don't use: ?auth=TOKEN
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

## Monitoring and Logs

### Application Logs

```bash
# View all logs
docker-compose logs -f

# Specific service
docker-compose logs -f adcp-server
docker-compose logs -f admin-ui

# Inside container
docker exec -it adcp-server tail -f /tmp/mcp_server.log
```

### Audit Logs

All operations logged to database:
- Operation type and timestamp
- Principal and tenant IDs
- Success/failure status
- Detailed operation data
- Security violations tracked

Access via Admin UI Operations Dashboard.

### Health Monitoring

```bash
# Check service health
curl http://localhost:8080/health
curl http://localhost:8001/health

# Database status
docker exec postgres pg_isready

# Container status
docker ps
```

## Operations Troubleshooting

### Common Issues

1. **Login failures**
   - Check SUPER_ADMIN_EMAILS configuration
   - Verify OAuth credentials
   - Check redirect URI matches

2. **Missing data**
   - Verify tenant_id in session
   - Check database connections
   - Review audit logs

3. **Slow performance**
   - Check database indexes
   - Monitor container resources
   - Review query optimization

### Debug Mode

Enable detailed logging:

```bash
# In docker-compose.override.yml
environment:
  - FLASK_DEBUG=1
  - LOG_LEVEL=DEBUG
```

### Slack Integration Issues

If notifications aren't working:

1. Verify webhook URL in tenant settings
2. Check notification types are enabled
3. Test webhook manually:
   ```bash
   curl -X POST "your-webhook-url" \
     -H "Content-Type: application/json" \
     -d '{"text": "Test notification"}'
   ```

## Testing Issues

### Pre-commit Hook "Excessive Mocking" Failure

**Cause**: Test file has more than 10 mocks (detected via `@patch|MagicMock|Mock()` count)

**Fix**: Apply mock reduction patterns:
1. Create centralized `MockSetup` class for duplicate mock creation
2. Use `patch.multiple()` helper methods to consolidate patches
3. Move database testing to integration tests with real DB connections
4. Focus mocking on external dependencies only (APIs, third-party services)

See `docs/testing/mock-reduction-patterns.md` for detailed examples.

### Tests Failing After Mock Refactoring

**Common Causes**:
- Missing imports: Add `from src.core.main import function_name`
- Mock return type mismatches: Ensure mocks return correct data types (list, dict, not Mock)
- Schema validation errors: Update test data to match current model requirements
- Test class naming: Rename `TestModel` classes to `ModelClass` to avoid pytest collection

### Integration Tests Slow or Flaky

**Fix**: Use proper database session management and isolation
**Pattern**: Create/cleanup test data in fixtures rather than mocking database calls

### Async Test Failures

**Fix**: Ensure proper `@pytest.mark.asyncio` and `AsyncMock` usage
**Pattern**: Use `async with` for async context managers, `await` for all async calls

## Testing Backend Issues

### Testing Hooks Not Working

**Issue**: X-Dry-Run, X-Mock-Time headers not being processed

**Cause**: Headers not being extracted from FastMCP context properly
**Fix**: Use `context.meta.get("headers", {})` to extract headers from FastMCP context

### Response Headers Missing

**Issue**: X-Next-Event, X-Next-Event-Time, X-Simulated-Spend headers not in response

**Cause**: Response headers not being set after apply_testing_hooks
**Fix**: Ensure `campaign_info` dict is passed to testing hooks for event calculation

### Session Isolation Not Working

**Issue**: Parallel tests interfering with each other

**Cause**: Missing or incorrect X-Test-Session-ID header
**Fix**: Generate unique session IDs per test and include in all requests

## Production Issues

### "operator does not exist: text < timestamp with time zone"

**Cause**: Database schema mismatch - columns created as TEXT instead of TIMESTAMP WITH TIME ZONE
**Root Cause**: Deprecated task system with conflicting schema definitions
**Fix**: Migrate to unified workflow system and eliminate task tables
**Prevention**: Use consistent schema definitions and avoid dual systems

### "Can't locate revision identified by '[revision_id]'"

**Cause**: Broken Alembic migration chain with missing or incorrect revision links
**Symptoms**: App crashes on startup, deployment failures, migration errors

**Fix Process**:
1. Check migration history: `alembic history`
2. Identify last known good revision
3. Reset to good revision: `alembic stamp [good_revision]`
4. Create new migration with correct `down_revision`
5. Deploy migration fix before code changes

**Prevention**: Never modify committed migration files, always test migrations locally

### Production Crashes After PR Merge

**Debugging Process**:
1. Check deployment status: `fly status --app adcp-sales-agent`
2. Review logs: `fly logs --app adcp-sales-agent`
3. Identify specific error patterns (database, import, runtime)
4. Check git history for recent changes
5. Test fixes locally before deploying

**Recovery**: Deploy minimal fix first, then implement broader changes

## Schema Alignment Issues

### AttributeError on Model Fields

**Symptoms**: `AttributeError: 'Creative' object has no attribute 'format_id'`

**Common Causes**:
- Field removed in schema migration
- Wrong data type assumptions
- JSONB updates not persisting
- Tests passing locally but failing in CI

**Prevention**:
1. Always use `attributes.flag_modified()` for JSONB updates
2. Update all three layers when refactoring: Database schema, ORM model, MCP tools
3. Use pre-commit schema validation hooks
4. Test BOTH model creation AND updates

See `docs/development/schema-alignment.md` for detailed patterns.

## GAM Inventory Sync Issues (FIXED - Sep 2025)

**Historical Issue**: Inventory browser returned `{"error": "Not yet implemented"}`

**Root Causes**:
1. Import path issues from code reorganization
2. Missing endpoint registration
3. Route conflicts

**Prevention**: Always use absolute imports and verify endpoint registration for new services

## Port Conflicts

**Solution**: Update `.env` file:
```bash
ADMIN_UI_PORT=8001  # Change from conflicting port
ADCP_SALES_PORT=8080
A2A_PORT=8091
```

## Additional Resources

- **Testing Patterns**: `docs/testing/`
- **A2A Implementation**: `docs/a2a-implementation-guide.md`
- **Security Guide**: `docs/security.md`
- **Architecture**: `docs/ARCHITECTURE.md`
