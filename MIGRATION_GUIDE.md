# Migration Guide

## Migrating from Single-Tenant to Multi-Tenant

### Overview

The AdCP:Buy server now uses a multi-tenant architecture by default. This guide helps existing users migrate their data.

### What Changed?

1. **No more config.json** - Configuration is now stored in the database per tenant
2. **Persistent SQLite location** - Database moved from `./adcp.db` to `~/.adcp/adcp.db`
3. **Multi-tenant by default** - All data is now associated with a tenant

### Migration Steps

#### 1. Backup Existing Data

```bash
# Backup your existing database
cp adcp.db adcp_backup.db

# Export as SQL (optional)
sqlite3 adcp.db .dump > adcp_backup.sql
```

#### 2. Update Dependencies

```bash
# Update to latest version
git pull

# Install new dependencies
uv sync
```

#### 3. Automatic Migration

When you run the new version, it will:
1. Create a default tenant using your existing config
2. Migrate existing data to the new location
3. Set up authentication tokens

```bash
# Run the server - it will auto-migrate
uv run python run_server.py
```

#### 4. Save Your Tokens

After migration, you'll see:
```
╔══════════════════════════════════════════════════════════════════╗
║                    🚀 ADCP:BUY SERVER INITIALIZED                ║
╠══════════════════════════════════════════════════════════════════╣
║  🔑 Admin Token (x-adcp-auth header):                            ║
║     [YOUR_ADMIN_TOKEN]                                           ║
╚══════════════════════════════════════════════════════════════════╝
```

**IMPORTANT**: Save this admin token! You'll need it for admin operations.

### Manual Migration (If Needed)

If automatic migration fails:

```bash
# 1. Move database to new location
mkdir -p ~/.adcp
cp adcp.db ~/.adcp/

# 2. Start fresh and create tenant
uv run python database.py
uv run python setup_tenant.py "Your Publisher Name" \
  --adapter mock  # or your adapter

# 3. Import old data (requires custom script)
```

### Configuration Migration

Your old `config.json` settings are now per-tenant:

| Old (config.json) | New (Per-Tenant) |
|-------------------|------------------|
| `ad_server.adapter` | `adapters.[adapter].enabled` |
| `gemini_api_key` | Environment: `GEMINI_API_KEY` |
| `creative_engine` | `tenant.config.creative_engine` |
| `admin.token` | `tenant.config.admin_token` |

### Using Different Databases

For production, consider PostgreSQL:

```bash
# Set up PostgreSQL
export DATABASE_URL=postgresql://user:pass@localhost/adcp

# Migrate SQLite to PostgreSQL
uv run python migrate_db.py --from sqlite --to postgresql
```

### Troubleshooting

#### "Database not found" Error

The database is now at `~/.adcp/adcp.db`, not `./adcp.db`.

#### "Missing config.json" Error

Configuration is now in the database. Use `setup_tenant.py` to configure.

#### Authentication Errors

Use the admin token shown during setup or check:
```bash
sqlite3 ~/.adcp/adcp.db "SELECT config FROM tenants WHERE tenant_id='default';"
```

### Benefits of Migration

1. **Multi-Publisher Support** - Host multiple publishers on one server
2. **Better Security** - Per-tenant data isolation
3. **Cloud Ready** - Support for PostgreSQL/MySQL
4. **Hot Configuration** - Change settings without restart
5. **Persistent Data** - No accidental overwrites during updates

### Need Help?

- Check logs in `audit_logs/` directory
- Review [Database Configuration](docs/database-configuration.md)
- See [Multi-Tenant Architecture](docs/multi-tenant-architecture.md)

### Rollback Plan

If you need to rollback:

```bash
# Restore old code
git checkout [previous-version]

# Restore database
cp adcp_backup.db adcp.db

# Restore config.json
cp config.json.backup config.json

# Run old version
uv run python run_server.py
```