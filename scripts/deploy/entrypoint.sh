#!/bin/bash
set -e

echo "🚀 Starting AdCP Sales Agent..."

# Function to check if database is accessible
check_database_health() {
    echo "🔍 Checking database connectivity..."
    echo "Python path: $(which python)"
    echo "Python version: $(python --version)"
    echo "Checking if psycopg2 is available..."
    python -c "import psycopg2; print('✅ psycopg2 imported successfully')" || (echo "❌ psycopg2 not available"; exit 1)
    python -c "
from src.core.database.db_config import get_db_connection
try:
    conn = get_db_connection()
    cursor = conn.execute('SELECT 1')
    result = cursor.fetchone()
    conn.close()
    print('✅ Database connection successful')
except Exception as e:
    print(f'❌ Database connection failed: {e}')
    exit(1)
    "
}

# Check database health first
check_database_health

# Run database migrations
echo "📦 Running database migrations..."
if ! python scripts/ops/migrate.py; then
    echo "⚠️  Database migration failed - continuing with startup..."
    echo "ℹ️  This may be due to a known migration chain issue with f7e503a712cf"
    echo "ℹ️  Application will continue to start - database schema should be current"
fi

# Check for common schema issues (report only, don't fail)
echo "🔍 Checking for known schema issues..."
python -c "
from src.core.database.db_config import get_db_connection
import json

issues = []
conn = get_db_connection()

# Check for commonly missing columns
checks = [
    ('media_buys', 'context_id'),
    ('creative_formats', 'updated_at'),
]

for table, column in checks:
    try:
        cursor = conn.execute(f\"\"\"
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = '{table}' AND column_name = '{column}'
        \"\"\")
        if not cursor.fetchone():
            issues.append(f'Missing column: {table}.{column}')
    except:
        # SQLite doesn't have information_schema, skip check
        pass

if issues:
    print('⚠️  Schema issues detected (non-critical):')
    for issue in issues:
        print(f'   - {issue}')
else:
    print('✅ No known schema issues detected')

conn.close()
" || true  # Don't fail on error

# Initialize database (safe - only creates data if tables are empty)
echo "📦 Initializing database schema and default data..."
echo "ℹ️  Note: init_db() is safe - it only creates tables (IF NOT EXISTS) and default tenant (if no tenants exist)"
if ! python -c "from src.core.database.database import init_db; init_db(exit_on_error=True)"; then
    echo "❌ Database initialization failed"
    exit 1
fi

# NOTE: CI/test data (init_database_ci.py) should be run by pytest fixtures, NOT in entrypoint
# Running it here causes race conditions when multiple containers start simultaneously

# Start all services (MCP, Admin UI, ADK, nginx)
echo "🌐 Starting all services with unified routing..."
exec python scripts/deploy/run_all_services.py
