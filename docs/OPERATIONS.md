# Operations Guide

## Admin UI Overview

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

## Publisher (Tenant) Management

### Creating Publishers

```bash
# With Google Ad Manager
docker exec -it adcp-server python setup_tenant.py "Publisher Name" \
  --adapter google_ad_manager \
  --gam-network-code 123456 \
  --gam-refresh-token YOUR_TOKEN

# With Mock adapter for testing
docker exec -it adcp-server python setup_tenant.py "Test Publisher" \
  --adapter mock
```

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

## Advertiser (Principal) Management

Advertisers are configured per-principal, not per-tenant:

1. Login to Admin UI
2. Select publisher/tenant
3. Go to "Advertisers" tab
4. Click "Add Advertiser"
5. Configure:
   - Name and contact info
   - Platform mappings (GAM advertiser ID, etc.)
   - API access token

Each advertiser gets unique MCP API credentials.

## Product Management

### AI-Powered Product Creation

The system uses Gemini to analyze descriptions and suggest configurations:

```bash
# Quick create from templates
curl -X POST -H "Cookie: session=..." \
  -d '{"product_ids": ["run_of_site_display", "homepage_takeover"]}' \
  "http://localhost:8001/api/tenant/TENANT_ID/products/quick-create"

# Get AI suggestions
curl -H "Cookie: session=..." \
  "http://localhost:8001/api/tenant/TENANT_ID/products/suggestions?industry=news"
```

### Default Products

New tenants get 6 standard products:
- Run of Site Display
- Homepage Takeover
- Video Pre-roll
- Native Content
- Mobile Interstitial
- Podcast Sponsorship

### Bulk Operations

Upload products via CSV:
```csv
name,description,pricing_type,base_price,min_spend
Premium Video,Above-fold video,cpm,45.00,5000
Native Posts,In-feed native,cpm,25.00,2500
```

## Creative Management

### Auto-Approval Workflow

1. Configure auto-approve formats per tenant
2. Standard formats approved instantly
3. Non-standard sent to review queue
4. Admin reviews in UI
5. Email notifications on status change

### Creative Groups

Organize creatives across campaigns:
- Group by advertiser, campaign, or theme
- Share creatives across media buys
- Track performance by group

## Operations Dashboard

Monitor all system activity:

### Media Buys View
- Active campaigns with spend
- Status and performance metrics
- Filter by tenant, status, date
- Export to CSV

### Workflow Activity View
- Workflow steps requiring approval
- Human-in-the-loop workflow steps
- Step completion and progression
- Workflow audit trail

### Metrics Summary
- Total active campaigns
- Total spend across system
- Pending workflow steps count
- Success/failure rates

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

## Slack Integration

Configure per-tenant webhooks:

1. Go to tenant settings in Admin UI
2. Add Slack webhook URL
3. Configure notification types:
   - New media buys
   - Creative approvals needed
   - Task assignments
   - Errors and alerts

## Backup and Recovery

### PostgreSQL Backup

```bash
# Full backup
docker exec postgres pg_dump -U adcp_user adcp > backup.sql

# Compressed backup
docker exec postgres pg_dump -U adcp_user adcp | gzip > backup.sql.gz

# Restore
docker exec -i postgres psql -U adcp_user adcp < backup.sql
```

### SQLite Backup

```bash
# Simple copy
cp adcp_local.db backup.db

# With active connections
sqlite3 adcp_local.db ".backup backup.db"
```

## Troubleshooting Operations

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

## Production Considerations

### Security
- Always use HTTPS in production
- Rotate API tokens regularly
- Monitor audit logs for anomalies
- Keep dependencies updated
- Input validation enforced on all API endpoints
- ID formats validated to prevent injection attacks
- Timezone strings validated against pytz database
- Temporary files cleaned up with try/finally blocks
- Database queries use parameterized statements only

### Performance
- Use PostgreSQL for production
- Enable connection pooling
- Implement caching where appropriate
- Monitor resource usage

### Scaling
- Database replication for read scaling
- Load balancer for multiple app instances
- Consider CDN for static assets
- Queue system for async tasks
