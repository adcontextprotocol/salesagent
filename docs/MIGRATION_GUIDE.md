# Database Migration Guide

## Overview

This guide provides best practices for creating and testing database migrations to prevent the cascade failures experienced during the GAM inventory sync incident.

## Before Creating a Migration

### 1. Understand the Current Schema

```bash
# Check current schema
sqlite3 adcp_local.db ".schema"

# For PostgreSQL
psql -U adcp_user -d adcp -c "\d+"

# Check column definitions in code
grep -r "Column(" models.py
```

### 2. Plan the Migration

Before writing any code:
1. List all tables affected
2. List all columns being added/removed/modified
3. Search for all code references to affected columns
4. Plan the data migration strategy

## Creating a Migration

### 1. Generate Migration File

```bash
# Create new migration
alembic revision -m "description_of_change"

# This creates: alembic/versions/XXX_description_of_change.py
```

### 2. Migration Template

```python
"""Description of what this migration does

Revision ID: 010_meaningful_name
Revises: 009_previous_migration
Create Date: 2025-01-30

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '010_meaningful_name'
down_revision = '009_previous_migration'
branch_labels = None
depends_on = None


def upgrade():
    """Apply migration."""
    # 1. Schema changes first
    op.add_column('table_name', 
        sa.Column('new_column', sa.String(50), nullable=True)
    )
    
    # 2. Data migration
    connection = op.get_bind()
    result = connection.execute(
        sa.text("SELECT id, old_column FROM table_name")
    )
    
    for row in result:
        connection.execute(
            sa.text(
                "UPDATE table_name SET new_column = :value WHERE id = :id"
            ),
            {"value": transform(row.old_column), "id": row.id}
        )
    
    # 3. Clean up old schema
    op.drop_column('table_name', 'old_column')
    
    # 4. Add constraints
    op.alter_column('table_name', 'new_column', nullable=False)


def downgrade():
    """Revert migration."""
    # Reverse of upgrade, in reverse order
    op.add_column('table_name',
        sa.Column('old_column', sa.String(100), nullable=True)
    )
    
    # Migrate data back
    connection = op.get_bind()
    # ... reverse data migration ...
    
    op.drop_column('table_name', 'new_column')
```

### 3. Common Patterns

#### Removing a Column Safely

```python
def upgrade():
    # First ensure no code references the column
    # Run: grep -r "column_name" . --include="*.py"
    
    # Then remove it
    op.drop_column('table_name', 'column_name')

def downgrade():
    # Restore with appropriate default
    op.add_column('table_name',
        sa.Column('column_name', sa.Text, 
                  server_default='{}', nullable=False)
    )
```

#### Changing Column Length

```python
def upgrade():
    # PostgreSQL and SQLite compatible way
    with op.batch_alter_table('table_name') as batch_op:
        batch_op.alter_column('column_name',
            type_=sa.String(50),  # new length
            existing_type=sa.String(20)  # old length
        )
```

#### Moving Data Between Columns

```python
def upgrade():
    # Add new structure
    op.add_column('tenants', sa.Column('gam_network_code', sa.String(50)))
    
    # Migrate data
    tenants_table = sa.table('tenants',
        sa.column('tenant_id', sa.String),
        sa.column('config', sa.Text),
        sa.column('gam_network_code', sa.String)
    )
    
    connection = op.get_bind()
    for tenant in connection.execute(sa.select([tenants_table])):
        if tenant.config:
            import json
            config = json.loads(tenant.config)
            gam_config = config.get('adapters', {}).get('google_ad_manager', {})
            
            connection.execute(
                tenants_table.update()
                .where(tenants_table.c.tenant_id == tenant.tenant_id)
                .values(gam_network_code=gam_config.get('network_code'))
            )
```

## Testing Migrations

### 1. Pre-Migration Checklist

```bash
# 1. Check for code references to changed columns
./scripts/check_schema_references.py

# 2. Run existing tests
pytest

# 3. Backup database
cp adcp_local.db adcp_local.backup.db
```

### 2. Test Migration Script

```bash
# Run the comprehensive test
./scripts/test_migration.sh --full-workflow --rollback

# Or test individually:

# Test upgrade
python migrate.py

# Test downgrade
alembic downgrade -1

# Test upgrade again
python migrate.py
```

### 3. Test with Both Databases

```bash
# SQLite
DATABASE_URL=sqlite:///test.db python migrate.py

# PostgreSQL (in Docker)
docker-compose up -d postgres
DATABASE_URL=postgresql://user:pass@localhost/test python migrate.py
```

### 4. Test Application Functionality

```python
# Create test script: test_after_migration.py
import asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

async def test_critical_paths():
    """Test critical application paths after migration."""
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    
    with SessionLocal() as db:
        # Test tenant access
        tenants = db.query(Tenant).all()
        for tenant in tenants:
            # Verify new structure works
            assert hasattr(tenant, 'gam_network_code')
            assert not hasattr(tenant, 'config')
        
        # Test inventory operations
        inventory = db.query(GAMInventory).first()
        if inventory:
            assert len(inventory.inventory_type) <= 30
    
    # Test full sync workflow
    from gam_inventory_service import GAMInventoryService
    service = GAMInventoryService()
    # ... test sync ...

asyncio.run(test_critical_paths())
```

## Post-Migration Verification

### 1. Verify Schema

```sql
-- Check migration was applied
SELECT * FROM alembic_version;

-- Verify schema changes
-- SQLite
.schema table_name

-- PostgreSQL
\d+ table_name
```

### 2. Verify Data

```sql
-- Check data migration worked
SELECT COUNT(*) FROM table_name WHERE new_column IS NOT NULL;

-- Check for any anomalies
SELECT * FROM table_name WHERE new_column IS NULL OR new_column = '';
```

### 3. Monitor Application

```bash
# Watch logs for errors
docker-compose logs -f adcp-server

# Check error tracking (if configured)
# Check application metrics
```

## Rollback Procedures

### 1. Immediate Rollback

```bash
# If migration fails immediately
alembic downgrade -1

# Restore from backup if needed
cp adcp_local.backup.db adcp_local.db
```

### 2. Rollback After Deployment

```bash
# 1. Stop application
docker-compose stop adcp-server

# 2. Rollback database
alembic downgrade <previous_revision>

# 3. Deploy previous code version
git checkout <previous_tag>
docker-compose build
docker-compose up -d
```

## Prevention Checklist

Before merging any PR with migrations:

- [ ] Migration tested with both SQLite and PostgreSQL
- [ ] All code references to changed schema updated
- [ ] Integration tests pass
- [ ] Migration can be rolled back cleanly
- [ ] Performance impact assessed (for large tables)
- [ ] Column length validations added to Pydantic models
- [ ] Pre-commit hooks pass
- [ ] Documentation updated

## Common Pitfalls to Avoid

1. **Don't assume column exists**: Always check before dropping
2. **Don't forget data migration**: Schema changes often need data movement
3. **Don't ignore rollback**: Every upgrade needs a working downgrade
4. **Don't mix concerns**: One migration = one logical change
5. **Don't forget defaults**: New NOT NULL columns need defaults
6. **Don't ignore existing data**: Test with production-like data
7. **Don't skip integration tests**: Unit tests aren't enough

## Emergency Contacts

If a migration causes production issues:

1. First: Try rollback procedure above
2. Second: Check #adcp-oncall Slack channel
3. Third: Page on-call engineer via PagerDuty

Remember: It's better to delay a migration than to break production!