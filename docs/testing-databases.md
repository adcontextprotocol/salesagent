# Database Testing: SQLite vs PostgreSQL

## The Problem

We've been catching database compatibility issues in CI that weren't caught during local development. This happens because:

1. **Local development**: Uses PostgreSQL (via Docker Compose)
2. **Local tests**: Default to SQLite (via `conftest.py`)
3. **CI tests**: Use PostgreSQL

## Key Differences Between SQLite and PostgreSQL

### 1. NOT NULL Constraints
- **SQLite**: More lenient, may accept NULL in some edge cases
- **PostgreSQL**: Strict enforcement of NOT NULL constraints
- **Example**: `updated_at NOT NULL` - SQLite might let it slide, PostgreSQL won't

### 2. Timestamp Functions
- **SQLite**: `datetime('now')`
- **PostgreSQL**: `CURRENT_TIMESTAMP`, `NOW()`
- **Fix**: Use database detection to choose the right function

### 3. JSONB Handling
- **SQLite**: Stores JSON as text
- **PostgreSQL**: Native JSONB type with operators
- **Impact**: JSON queries behave differently

### 4. Boolean Values
- **SQLite**: Uses 0/1
- **PostgreSQL**: Uses true/false
- **Fix**: Use proper boolean values in Python, let the driver handle conversion

### 5. ALTER TABLE Operations
- **SQLite**: Limited support, requires batch mode for many operations
- **PostgreSQL**: Full ALTER TABLE support
- **Impact**: Alembic migrations may fail on SQLite

## Solutions

### 1. Run Tests with PostgreSQL Locally

```bash
# Use the provided script
./run_tests_postgresql.sh

# Or manually:
DATABASE_URL=postgresql://adcp_user:secure_password_change_me@localhost:5521/adcp \
DB_TYPE=postgresql \
uv run pytest
```

### 2. Use Test Containers

For isolated PostgreSQL testing:

```bash
# Start a test PostgreSQL
docker run -d --name test-pg \
  -e POSTGRES_PASSWORD=test \
  -p 5433:5432 \
  postgres:15

# Run tests
DATABASE_URL=postgresql://postgres:test@localhost:5433/postgres \
uv run pytest

# Cleanup
docker stop test-pg && docker rm test-pg
```

### 3. Database-Agnostic Code

When writing SQL:

```python
# Bad - SQLite specific
conn.execute("INSERT INTO table (created_at) VALUES (datetime('now'))")

# Good - Database agnostic
if conn.config['type'] == 'sqlite':
    timestamp_func = "datetime('now')"
else:
    timestamp_func = "CURRENT_TIMESTAMP"
conn.execute(f"INSERT INTO table (created_at) VALUES ({timestamp_func})")
```

### 4. Test Both Databases

Before submitting PRs:

1. Run tests with default SQLite: `uv run pytest`
2. Run tests with PostgreSQL: `./run_tests_postgresql.sh`
3. Check CI results match local PostgreSQL results

## Common Pitfalls

1. **Missing columns**: PostgreSQL is strict about all NOT NULL columns being provided
2. **Function names**: SQLite functions don't exist in PostgreSQL and vice versa
3. **Type casting**: PostgreSQL may require explicit casts where SQLite doesn't
4. **Transaction handling**: Behavior differs between databases

## Recommendations

1. **Default to PostgreSQL for tests** when possible, since production uses PostgreSQL
2. **Keep CI and local test environments aligned**
3. **Document database-specific code** with comments
4. **Use SQLAlchemy or similar ORMs** when possible to abstract differences
5. **Test migrations on both databases** before committing