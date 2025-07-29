# Operations Dashboard Guide

## Overview

The Operations Dashboard provides comprehensive real-time monitoring and management of all advertising operations within the AdCP Sales Agent. It's accessible through the Admin UI and offers complete visibility into media buys, tasks, and system activity.

## Accessing the Dashboard

1. Navigate to the Admin UI: `http://localhost:8001`
2. Login with Google OAuth
3. Select a tenant
4. Click "Operations Dashboard" in the navigation

## Dashboard Features

### Summary Cards

The dashboard displays key metrics at the top:
- **Active Media Buys**: Number of currently running campaigns
- **Total Active Spend**: Sum of budgets for all active campaigns
- **Pending Tasks**: Number of tasks awaiting completion
- **Failed Tasks**: Number of tasks that failed execution

### Media Buys Tab

View and filter all media buys with:
- **Real-time Filtering**: Filter by status (draft, pending, active, paused, completed)
- **Detailed Information**: 
  - Media Buy ID
  - Order Name
  - Advertiser
  - Principal
  - Budget
  - Flight Dates
  - Current Status
  - Creation Time
- **Status Indicators**: Color-coded status badges for quick identification

### Tasks Tab

Monitor all system tasks:
- **Task Types**: Various operation types (update_media_buy, create_line_item, etc.)
- **Status Tracking**: pending, in_progress, completed, failed
- **Associated Media Buys**: Direct links to related campaigns
- **Timing Information**: Created and updated timestamps
- **Task Details**: Full JSON details for debugging

### Audit Logs Tab

Complete audit trail with:
- **Operation Tracking**: Every API call and system operation
- **Security Monitoring**: Highlighted authentication failures
- **Principal Context**: Who performed each action
- **Success/Failure Status**: Clear indicators with error messages
- **Detailed Logging**: Full request/response data for compliance
- **Timestamp Precision**: Exact timing of all operations

## Key Features

### Database Persistence

All operational data is now stored in the database:
- **media_buys table**: Full campaign configuration and status
- **tasks table**: Task queue with progress tracking
- **audit_logs table**: Complete audit trail with tenant isolation

### Real-time Updates

The dashboard uses JavaScript for live filtering:
- No page reloads required
- Instant status filtering
- Responsive table updates

### Multi-Tenant Isolation

All data is scoped by tenant:
- Each tenant sees only their own operations
- Super admins can switch between tenants
- Complete data isolation at database level

## Use Cases

### Campaign Monitoring
- Track all active media buys in one place
- Monitor budget utilization
- Identify stalled or failed campaigns

### Task Management
- View pending manual approvals
- Track task completion status
- Debug failed operations

### Security Auditing
- Review all system access
- Identify unauthorized attempts
- Maintain compliance records

### Performance Analysis
- Track operation success rates
- Identify system bottlenecks
- Monitor API usage patterns

## Best Practices

1. **Regular Monitoring**: Check the dashboard daily for pending tasks
2. **Task Resolution**: Address failed tasks promptly to avoid campaign delays
3. **Audit Review**: Periodically review audit logs for security events
4. **Database Maintenance**: Implement log rotation for audit_logs table
5. **Status Filtering**: Use filters to focus on specific campaign states

## Technical Implementation

The Operations Dashboard is implemented with:
- **Backend**: Flask routes in `admin_ui.py`
- **Frontend**: Responsive HTML/JavaScript in `templates/operations.html`
- **Database**: PostgreSQL/SQLite with proper indexing
- **Security**: OAuth authentication with role-based access

## Troubleshooting

### Common Issues

1. **No Data Showing**
   - Verify database connection
   - Check tenant_id is correct
   - Ensure tables are properly initialized

2. **Slow Performance**
   - Add database indexes on frequently queried columns
   - Implement pagination for large datasets
   - Consider archiving old audit logs

3. **Filter Not Working**
   - Check JavaScript console for errors
   - Verify data attributes on table rows
   - Ensure status values match expected format

### Database Queries

Key queries used by the dashboard:

```sql
-- Active media buys summary
SELECT COUNT(*), SUM(budget) 
FROM media_buys 
WHERE tenant_id = ? AND status = 'active';

-- Recent audit logs
SELECT * FROM audit_logs 
WHERE tenant_id = ? 
ORDER BY timestamp DESC 
LIMIT 100;

-- Pending tasks
SELECT * FROM tasks 
WHERE tenant_id = ? AND status = 'pending'
ORDER BY created_at ASC;
```

## Future Enhancements

Planned improvements include:
- Export functionality (CSV/Excel)
- Advanced search and filtering
- Graphical charts and trends
- Email notifications for task assignments
- Webhook integrations for external monitoring