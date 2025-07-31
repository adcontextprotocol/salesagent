# Database Migrations Guide

The AdCP Sales Agent uses Alembic for database schema version control and migrations. This ensures that database schema changes are tracked, versioned, and can be applied consistently across different environments.

## Overview

- **Migration Tool**: Alembic (SQLAlchemy's migration framework)
- **Supported Databases**: SQLite (development) and PostgreSQL (production)
- **Migration Location**: `/alembic/versions/`
- **Configuration**: `alembic.ini` and `alembic/env.py`

## How It Works

1. **Automatic Migrations**: When the server starts (via Docker or directly), migrations are automatically applied
2. **Schema Tracking**: Each migration has a unique ID and tracks schema changes
3. **Version Control**: All migrations are tracked in git
4. **Rollback Support**: Migrations can be rolled back if needed

## Common Operations

### Running Migrations

```bash
# Run all pending migrations (default action)
python migrate.py

# Or explicitly
python migrate.py upgrade
```

### Checking Migration Status

```bash
# See current migration version
python migrate.py status
```

### Creating a New Migration

When you make schema changes:

1. Update the SQLAlchemy models in `models.py`
2. Generate a migration:

```bash
python migrate.py create "Add new_column to products table"
```

3. Review the generated migration in `alembic/versions/`
4. Commit both the model changes and migration file

### Manual Migration Commands

For advanced usage with Alembic directly:

```bash
# Create virtual environment and activate it
uv venv
source .venv/bin/activate

# Generate migration
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View history
alembic history
```

## Docker Integration

The Docker setup automatically runs migrations on startup:

1. The `entrypoint.sh` script runs `python migrate.py` before starting the server
2. This ensures the database is always up-to-date
3. No manual intervention needed in production

## Development Workflow

1. **Make Schema Changes**: Update `database_schema.py` with new SQL
2. **Update Models**: Modify `models.py` to match
3. **Generate Migration**: `python migrate.py create "Your description"`
4. **Test Migration**: Run `python migrate.py` to apply
5. **Commit Changes**: Include both code and migration files

## Environment Configuration

The migration system uses the same database configuration as the main application:

- **SQLite**: Uses `DATA_DIR` environment variable (default: `~/.adcp/adcp.db`)
- **PostgreSQL**: Uses `DATABASE_URL` or individual `DB_*` variables
- **Docker**: Automatically configured via `docker-compose.yml`

## Troubleshooting

### Migration Conflicts

If you get migration conflicts:
1. Check `alembic/versions/` for duplicate migrations
2. Ensure your branch is up-to-date with main
3. Resolve conflicts in migration files manually

### Database Connection Issues

- Verify database credentials in environment variables
- Check if database server is running
- For Docker, ensure postgres service is healthy

### Schema Mismatch

If the database schema doesn't match models:
1. Generate a new migration to fix discrepancies
2. Or drop and recreate the database (development only)

## Best Practices

1. **Always Review Migrations**: Check generated migrations before applying
2. **Test Locally First**: Run migrations in development before production
3. **Backup Before Major Changes**: Always backup production database
4. **Keep Migrations Small**: One logical change per migration
5. **Document Complex Changes**: Add comments in migration files

## Migration File Structure

Each migration file contains:
- `revision`: Unique identifier
- `down_revision`: Previous migration ID
- `upgrade()`: Function to apply changes
- `downgrade()`: Function to rollback changes

Example:
```python
"""Add countries column to products

Revision ID: abc123
Revises: def456
Create Date: 2024-01-15 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'abc123'
down_revision = 'def456'

def upgrade():
    op.add_column('products', 
        sa.Column('countries', sa.JSON(), nullable=True))

def downgrade():
    op.drop_column('products', 'countries')
```