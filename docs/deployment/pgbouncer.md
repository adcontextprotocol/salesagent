# PgBouncer Configuration for Fly.io Managed Postgres

This guide explains how to configure the AdCP Sales Agent to use PgBouncer with Fly.io's managed PostgreSQL.

## Why PgBouncer?

PgBouncer is a lightweight connection pooler for PostgreSQL that provides:
- **Efficient connection pooling**: Reduces database overhead
- **Better scalability**: Handles more concurrent connections
- **Resource optimization**: Fewer idle connections to the database
- **Built-in with Fly.io**: Automatically available with Fly Postgres

## Configuration

### 1. Fly.io Managed Postgres Setup

When you create a Fly Postgres database, PgBouncer is automatically included and exposed on port **6543**.

```bash
# Create a Fly Postgres cluster (if not already created)
fly postgres create --name adcp-postgres

# Attach it to your app
fly postgres attach adcp-postgres --app adcp-sales-agent
```

This creates a `DATABASE_URL` secret with the direct PostgreSQL connection (port 5432).

### 2. Update DATABASE_URL to Use PgBouncer

Update your app's `DATABASE_URL` to use port **6543** instead of 5432:

```bash
# Get current DATABASE_URL
fly secrets list --app adcp-sales-agent

# Update to use PgBouncer port (6543 instead of 5432)
fly secrets set DATABASE_URL="postgres://user:password@host.internal:6543/dbname" --app adcp-sales-agent
```

**Important**: Change `:5432` to `:6543` in the connection string.

### 3. Automatic Detection

The application automatically detects PgBouncer usage in two ways:

1. **Port-based detection**: If `:6543` is in the `DATABASE_URL`
2. **Environment variable**: Set `USE_PGBOUNCER=true`

No additional configuration needed - the app will automatically:
- Use smaller connection pool (2 connections + 5 overflow)
- Disable `pool_pre_ping` (incompatible with PgBouncer transaction pooling)
- Use shorter connection recycling (5 minutes instead of 1 hour)

### 4. Verify Configuration

After deployment, check the logs to confirm PgBouncer is detected:

```bash
fly logs --app adcp-sales-agent | grep "PgBouncer detected"
```

You should see:
```
PgBouncer detected - using optimized connection pool settings
```

## PgBouncer vs Direct Connection

### PgBouncer (Port 6543)
- **Pool Size**: 2 connections + 5 overflow = 7 max
- **Pre-ping**: Disabled (not needed with PgBouncer)
- **Recycle**: 300 seconds (5 minutes)
- **Best for**: Production with managed Postgres

### Direct PostgreSQL (Port 5432)
- **Pool Size**: 10 connections + 20 overflow = 30 max
- **Pre-ping**: Enabled (tests connections before use)
- **Recycle**: 3600 seconds (1 hour)
- **Best for**: Development, local testing

## Connection Pooling Modes

PgBouncer on Fly.io uses **transaction pooling** by default:
- ✅ Most efficient
- ✅ Works with SQLAlchemy
- ⚠️ Incompatible with `pool_pre_ping` (hence we disable it)
- ⚠️ Session-level prepared statements not preserved

Our configuration is optimized for transaction pooling mode.

## Troubleshooting

### Connection Issues

If you see connection errors after switching to PgBouncer:

1. **Verify port**: Ensure `:6543` is in `DATABASE_URL`
```bash
fly secrets list --app adcp-sales-agent | grep DATABASE_URL
```

2. **Check PgBouncer status**:
```bash
fly postgres connect --app adcp-postgres
# Inside Postgres:
\c pgbouncer
SHOW POOLS;
SHOW CLIENTS;
```

3. **Check application logs**:
```bash
fly logs --app adcp-sales-agent
```

### Performance Issues

If you see "too many connections" errors:

1. **Increase PgBouncer pool size** (if needed):
```bash
# Connect to your Postgres cluster
fly ssh console --app adcp-postgres

# Edit PgBouncer config
vi /data/pgbouncer/pgbouncer.ini

# Adjust max_client_conn and default_pool_size
# Then restart PgBouncer
sv restart pgbouncer
```

2. **Monitor connection usage**:
```bash
fly postgres connect --app adcp-postgres
\c pgbouncer
SHOW STATS;
```

## Environment Variables

Optional environment variables for fine-tuning:

```bash
# Force PgBouncer mode (if port detection doesn't work)
USE_PGBOUNCER=true

# Connection timeouts (seconds)
DATABASE_CONNECT_TIMEOUT=10
DATABASE_QUERY_TIMEOUT=30
DATABASE_POOL_TIMEOUT=30
```

## Best Practices

1. **Always use PgBouncer in production** with Fly.io managed Postgres
2. **Monitor connection usage** with `SHOW STATS`
3. **Keep pool_size small** (2-5 connections) - PgBouncer does the pooling
4. **Use transaction pooling mode** (default on Fly.io)
5. **Disable pool_pre_ping** (incompatible with transaction pooling)

## Migration Checklist

Switching from direct Postgres to PgBouncer:

- [ ] Update `DATABASE_URL` to use port 6543
- [ ] Deploy application
- [ ] Verify "PgBouncer detected" in logs
- [ ] Test application functionality
- [ ] Monitor connection pool usage
- [ ] Confirm no connection errors

## Additional Resources

- [Fly.io Postgres Documentation](https://fly.io/docs/postgres/)
- [PgBouncer Documentation](https://www.pgbouncer.org/)
- [SQLAlchemy Pooling](https://docs.sqlalchemy.org/en/20/core/pooling.html)
