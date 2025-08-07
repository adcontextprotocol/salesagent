# AdCP Sync Cron Deployment Guide

This guide explains how to deploy automated sync jobs for AdCP using Fly.io or Docker.

## Overview

The sync cron job automatically syncs inventory from Google Ad Manager for all configured tenants on a regular schedule.

## Deployment Options

### Option 1: Fly.io Deployment

1. **Install Fly CLI**:
   ```bash
   curl -L https://fly.io/install.sh | sh
   ```

2. **Login to Fly**:
   ```bash
   fly auth login
   ```

3. **Deploy the cron app**:
   ```bash
   # From the project root
   fly launch --config fly-cron.toml --name adcp-sync-cron
   ```

4. **Set secrets**:
   ```bash
   fly secrets set DATABASE_URL="your-production-database-url" -a adcp-sync-cron
   ```

5. **Deploy updates**:
   ```bash
   fly deploy --config fly-cron.toml -a adcp-sync-cron
   ```

### Option 2: Docker Compose (Local/Development)

Add this service to your `docker-compose.yml`:

```yaml
  sync-cron:
    build:
      context: .
      dockerfile: Dockerfile.cron
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - ADMIN_UI_PORT=8001
    depends_on:
      - postgres
      - admin-ui
    networks:
      - adcp-network
```

Then run:
```bash
docker-compose up -d sync-cron
```

### Option 3: Kubernetes CronJob

Create a Kubernetes CronJob resource:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: adcp-sync
spec:
  schedule: "0 */6 * * *"  # Every 6 hours
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: sync
            image: your-registry/adcp-sync-cron:latest
            env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: adcp-secrets
                  key: database-url
          restartPolicy: OnFailure
```

## Cron Schedule

The default schedule in `crontab`:
- Every 6 hours: `0 */6 * * *`
- Daily at 2 AM EST: `0 7 * * *` (7 AM UTC)

To modify the schedule, edit the `crontab` file.

## Monitoring

### View logs (Fly.io):
```bash
fly logs -a adcp-sync-cron
```

### View sync history:
```bash
# Via API
curl -H "X-API-Key: your-superadmin-key" \
  https://your-domain.com/api/v1/sync/stats
```

### Check sync status in Admin UI:
1. Login to Admin UI
2. Go to main dashboard
3. View "Sync Status Overview" section

## Manual Sync

To manually trigger a sync for all tenants:

```bash
# SSH into container (Fly.io)
fly ssh console -a adcp-sync-cron

# Run sync script
python /app/scripts/sync_all_tenants.py
```

## Troubleshooting

### Common Issues

1. **Database connection errors**:
   - Verify DATABASE_URL is correct
   - Check network connectivity between cron container and database

2. **API authentication errors**:
   - Ensure superadmin API key exists in database
   - Run: `python -c "from sync_api import initialize_superadmin_api_key; print(initialize_superadmin_api_key())"`

3. **Sync failures**:
   - Check tenant has valid GAM credentials
   - Verify GAM refresh token is not expired
   - Check GAM API quotas

### Debug Mode

To run sync with verbose logging:

```bash
# Set log level
export LOG_LEVEL=DEBUG
python /app/scripts/sync_all_tenants.py
```

## Security Considerations

1. **Database Access**: The cron job needs read access to tenants and write access to sync_jobs table
2. **API Key**: The superadmin API key is auto-generated and stored in the database
3. **Network**: Ensure the cron container can reach the Admin UI API endpoints

## Customization

### Add custom sync logic

Edit `scripts/sync_all_tenants.py` to:
- Filter tenants by specific criteria
- Add pre/post sync hooks
- Send notifications on sync completion
- Implement retry logic

### Change sync frequency

Edit `crontab` with standard cron syntax:
```
# Every hour
0 * * * * python /app/scripts/sync_all_tenants.py

# Every day at midnight
0 0 * * * python /app/scripts/sync_all_tenants.py

# Every Monday at 3 AM
0 3 * * 1 python /app/scripts/sync_all_tenants.py
```