# Database Configuration Guide

## Overview

The AdCP Sales Agent server supports two database backends for flexibility in different deployment scenarios:

- **SQLite** (default) - Great for development and single-server deployments
- **PostgreSQL** - Recommended for production multi-tenant deployments

## Configuration Methods

### 1. Environment Variables (Recommended)

The simplest way is to set environment variables:

```bash
# SQLite (default)
export DB_TYPE=sqlite
export DATA_DIR=~/.adcp  # Persistent directory for SQLite file

# PostgreSQL
export DB_TYPE=postgresql
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=adcp
export DB_USER=adcp_user
export DB_PASSWORD=secure_password
export DB_SSLMODE=require  # For production
```

### 2. DATABASE_URL (Heroku/Cloud Compatible)

For cloud deployments, use a single DATABASE_URL:

```bash
# PostgreSQL
export DATABASE_URL=postgresql://user:password@host:5432/database?sslmode=require

# SQLite
export DATABASE_URL=sqlite:///path/to/database.db
```

## SQLite Configuration

### Default Behavior

By default, SQLite databases are stored in a persistent location:

```
~/.adcp/adcp.db
```

This prevents accidental data loss during updates.

### Custom Location

```bash
export DATA_DIR=/var/lib/adcp
# Database will be at /var/lib/adcp/adcp.db
```

### Docker Volumes

For Docker deployments, mount a volume:

```yaml
version: '3'
services:
  adcp:
    image: adcp-sales-agent
    volumes:
      - adcp-data:/root/.adcp
    environment:
      - DB_TYPE=sqlite

volumes:
  adcp-data:
```

## PostgreSQL Configuration

### Basic Setup

1. Create database and user:

```sql
CREATE DATABASE adcp;
CREATE USER adcp_user WITH ENCRYPTED PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE adcp TO adcp_user;
```

2. Configure environment:

```bash
export DB_TYPE=postgresql
export DB_HOST=postgres.example.com
export DB_PORT=5432
export DB_NAME=adcp
export DB_USER=adcp_user
export DB_PASSWORD=secure_password
export DB_SSLMODE=require
```

### Connection Pooling

For production, consider using a connection pooler like PgBouncer:

```bash
export DATABASE_URL=postgresql://user:pass@pgbouncer:6432/adcp?sslmode=prefer
```

### High Availability

PostgreSQL supports various HA configurations:
- Streaming replication
- Logical replication
- Patroni for automatic failover

## Migration Between Databases

### Export from SQLite

```bash
# Export data
sqlite3 ~/.adcp/adcp.db .dump > adcp_backup.sql

# Convert for PostgreSQL
sed -i 's/AUTOINCREMENT/SERIAL/g' adcp_backup.sql
sed -i 's/datetime(/now(/g' adcp_backup.sql
```

### Import to PostgreSQL

```bash
psql -U adcp_user -d adcp -f adcp_backup.sql
```

## Performance Considerations

### SQLite
- Good for up to 10,000 requests/day
- Single-writer limitation
- Enable WAL mode for better concurrency

### PostgreSQL
- Recommended for production
- Handles millions of requests/day
- Built-in connection pooling
- Advanced indexing options

## Backup Strategies

### SQLite

```bash
# Simple file copy (ensure no active connections)
cp ~/.adcp/adcp.db /backup/adcp_$(date +%Y%m%d).db

# Using SQLite backup command
sqlite3 ~/.adcp/adcp.db ".backup /backup/adcp_$(date +%Y%m%d).db"
```

### PostgreSQL

```bash
# Logical backup
pg_dump -U adcp_user -d adcp > adcp_backup.sql

# Compressed backup
pg_dump -U adcp_user -d adcp | gzip > adcp_backup.sql.gz

# Custom format (allows selective restore)
pg_dump -U adcp_user -d adcp -Fc > adcp_backup.dump
```

## Monitoring

### Health Check Endpoint

The server provides a health check that verifies database connectivity:

```bash
curl http://localhost:8080/health
```

### Database Metrics

Monitor these key metrics:
- Connection count
- Query response time
- Disk usage
- Replication lag (if applicable)

## Troubleshooting

### Connection Issues

1. Check environment variables:
```bash
env | grep DB_
```

2. Test connection manually:
```bash
# PostgreSQL
psql -h $DB_HOST -U $DB_USER -d $DB_NAME
```

3. Check logs for detailed errors

### Permission Issues

Ensure the database user has proper permissions:

```sql
-- PostgreSQL
GRANT ALL ON ALL TABLES IN SCHEMA public TO adcp_user;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO adcp_user;
```

### Migration Issues

If database schema is out of sync:

1. Export existing data
2. Drop and recreate tables
3. Re-import data
4. Run any migration scripts

## Best Practices

1. **Use PostgreSQL for Production** - Better performance and features
2. **Enable SSL/TLS** - Encrypt database connections
3. **Regular Backups** - Automate daily backups
4. **Monitor Performance** - Set up alerts for slow queries
5. **Test Migrations** - Always test database changes in staging
6. **Use Connection Pooling** - Reduce connection overhead
7. **Set Resource Limits** - Prevent runaway queries

## Docker Compose Example

```yaml
version: '3'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: adcp
      POSTGRES_USER: adcp_user
      POSTGRES_PASSWORD: secure_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  adcp:
    build: .
    environment:
      DB_TYPE: postgresql
      DB_HOST: postgres
      DB_PORT: 5432
      DB_NAME: adcp
      DB_USER: adcp_user
      DB_PASSWORD: secure_password
    depends_on:
      - postgres
    ports:
      - "8080:8080"

volumes:
  postgres_data:
```

This configuration provides a production-ready setup with PostgreSQL and proper data persistence.