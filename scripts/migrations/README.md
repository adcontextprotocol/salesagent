# Database Migrations

One-time data migration scripts for fixing data integrity issues.

## Available Migrations

### add_missing_pricing_options.py

**Problem**: Products created without pricing_options cause "Product has no pricing_options configured" errors.

**Solution**: Adds default pricing options to any products missing them:
- Guaranteed delivery products → Fixed CPM $15.00
- Non-guaranteed products → Auction CPM with $5.00 floor

**Usage**:
```bash
# Local development
uv run python scripts/migrations/add_missing_pricing_options.py

# Production (Fly.io)
fly ssh console --app adcp-sales-agent
cd /app
python scripts/migrations/add_missing_pricing_options.py
```

**Safe to run multiple times** - script checks for existing pricing options and skips them.

## When to Use Migrations

Use migration scripts when:
1. Database schema is correct but data is missing/incorrect
2. One-time bulk data fixes are needed
3. Rolling back would be difficult (vs. Alembic migrations)

**Do NOT use for**:
- Schema changes (use Alembic migrations instead)
- Regular maintenance tasks (use cron jobs/scheduled tasks)
- Data that should be created via API/Admin UI

## Creating New Migrations

1. Create script in `scripts/migrations/`
2. Add verification logic (check results)
3. Make idempotent (safe to run multiple times)
4. Document in this README
5. Test locally before production
