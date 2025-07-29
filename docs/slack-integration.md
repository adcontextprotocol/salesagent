# Slack Integration Guide

## Overview

The AdCP Sales Agent includes built-in Slack integration for real-time notifications about tasks, approvals, and system events. This helps teams stay informed and respond quickly to manual approval requests.

## Features

### Notification Types

1. **New Task Notifications**
   - Alerts when a new task requires human intervention
   - Includes task details, priority, and direct link to Admin UI
   - Highlights urgent and high-priority tasks

2. **Task Completion Notifications**
   - Confirms when tasks are completed or failed
   - Shows who completed the task and the resolution
   - Includes error details for failed tasks

3. **Creative Pending Approval**
   - Notifies when new creatives need review
   - Shows creative format and associated principal
   - Direct link to review in Admin UI

4. **Audit Log Notifications**
   - Sends audit logs to a separate Slack channel
   - Monitors failed operations and security violations
   - Alerts on sensitive operations (create/update media buys)
   - Highlights high-value transactions (>$10,000)

## Setup

### 1. Create Slack Webhook

1. Go to your Slack workspace's [App Directory](https://api.slack.com/apps)
2. Create a new app or select an existing one
3. Navigate to "Incoming Webhooks"
4. Activate Incoming Webhooks
5. Click "Add New Webhook to Workspace"
6. Select the channel for notifications
7. Copy the webhook URL

### 2. Configure Environment Variables

Set the webhook URLs as environment variables:

```bash
# Main notifications (tasks, creatives)
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

# Audit log notifications (optional, separate channel)
export SLACK_AUDIT_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/AUDIT/WEBHOOK"
```

Or add to your `.env` file:
```
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
SLACK_AUDIT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/AUDIT/WEBHOOK
```

### 3. Docker Configuration

For Docker deployments, add to your `docker-compose.yml`:

```yaml
services:
  adcp-server:
    environment:
      - SLACK_WEBHOOK_URL=${SLACK_WEBHOOK_URL}
      - SLACK_AUDIT_WEBHOOK_URL=${SLACK_AUDIT_WEBHOOK_URL}
```

## Message Formats

### New Task Notification

![New Task](slack-new-task.png)

```
🔔 New Task Requires Approval
Task ID: task_abc123
Type: Create Media Buy
Principal: Acme Corp
Tenant: Sports Publisher
[View in Admin UI]
```

### Task Completion

![Task Complete](slack-task-complete.png)

```
✅ Task Completed
Task ID: task_abc123
Type: Create Media Buy
Completed By: admin@example.com
Status: Completed
```

### Creative Pending

![Creative Pending](slack-creative-pending.png)

```
🎨 New Creative Pending Approval
Creative ID: creative_xyz789
Format: video
Principal: Acme Corp
Media Buy: mb_12345
[Review Creative]
```

### Audit Log Entry

![Audit Log](slack-audit-log.png)

```
📝 Audit Log
Operation: create_media_buy
Principal: Acme Corp
Tenant: Sports Publisher
Status: ✅ Success
Details:
• Media Buy ID: `mb_12345`
• Total Budget: `$50,000.00`
Logged at 2025-01-15 10:30:45 UTC | Adapter: mock
```

### Security Alert

![Security Alert](slack-security-alert.png)

```
🚨 Security Alert
Operation: update_media_buy
Principal: UNAUTHORIZED: unknown_user
Tenant: Sports Publisher
Status: ❌ Failed
Error: Security violation: Principal not found in system
Logged at 2025-01-15 10:30:45 UTC | Adapter: AdCP
```

## Testing

### Send Test Notification

You can test your Slack integration using curl:

```bash
curl -X POST $SLACK_WEBHOOK_URL \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "Test notification from AdCP Sales Agent",
    "blocks": [
      {
        "type": "section",
        "text": {
          "type": "mrkdwn",
          "text": "✅ Slack integration is working!"
        }
      }
    ]
  }'
```

### Verify in Application

1. Create a test media buy that requires manual approval
2. Check your Slack channel for the notification
3. Complete the task and verify completion notification

## Advanced Configuration

### Per-Tenant Webhooks

You can configure different webhook URLs per tenant by updating the tenant configuration:

```json
{
  "features": {
    "slack_webhook_url": "https://hooks.slack.com/services/TENANT/SPECIFIC/URL",
    "slack_audit_webhook_url": "https://hooks.slack.com/services/TENANT/AUDIT/URL"
  }
}
```

### Audit Log Filtering

The audit logger automatically sends notifications for:
- All failed operations
- Security violations
- Sensitive operations (create/update/delete media buys, creative approvals)
- High-value transactions (budgets over $10,000)

To customize notification criteria, modify the filtering logic in `audit_logger.py`.

### Channel Routing

To send different notification types to different channels:

1. Create multiple webhooks for different channels
2. Set environment variables:
   ```bash
   SLACK_WEBHOOK_TASKS=https://hooks.slack.com/services/TASKS/CHANNEL
   SLACK_WEBHOOK_CREATIVES=https://hooks.slack.com/services/CREATIVE/CHANNEL
   ```

### Custom Message Templates

The notification templates can be customized in `slack_notifier.py`:

```python
# Example: Add custom fields to task notifications
blocks.append({
    "type": "section",
    "fields": [
        {
            "type": "mrkdwn",
            "text": f"*Custom Field:*\n{custom_value}"
        }
    ]
})
```

## Security Considerations

1. **Webhook URLs are Sensitive**: Treat webhook URLs as secrets
2. **Use Environment Variables**: Never commit webhook URLs to version control
3. **Rotate Webhooks**: Periodically rotate webhook URLs
4. **Channel Permissions**: Ensure notification channels have appropriate access controls

## Troubleshooting

### Notifications Not Sending

1. Check webhook URL is correctly set:
   ```bash
   echo $SLACK_WEBHOOK_URL
   ```

2. Verify network connectivity to Slack
3. Check application logs for error messages
4. Test webhook directly with curl

### Message Formatting Issues

1. Ensure blocks follow Slack's Block Kit format
2. Validate JSON structure
3. Check for special characters that need escaping

### Rate Limiting

Slack has rate limits for incoming webhooks:
- 1 message per second sustained
- Brief bursts allowed

If you hit rate limits:
1. Implement message queuing
2. Batch similar notifications
3. Use thread replies for updates

## Integration with Other Tools

### Combine with Webhooks

You can use both Slack notifications and custom webhooks:

```python
# Send to Slack
slack_notifier.notify_new_task(...)

# Also send to custom webhook
if custom_webhook_url:
    send_custom_webhook(...)
```

### Zapier Integration

Use Zapier to:
1. Route notifications to other platforms
2. Create tickets in project management tools
3. Log events to spreadsheets

## Best Practices

1. **Use Threading**: Group related notifications in threads
2. **Actionable Messages**: Include direct links to take action
3. **Clear Formatting**: Use emoji and formatting for clarity
4. **Avoid Noise**: Only send essential notifications
5. **Test Regularly**: Ensure notifications work after updates