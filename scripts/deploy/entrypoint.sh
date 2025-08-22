#!/bin/bash
set -e

echo "🚀 Starting AdCP Sales Agent..."

# Function to check if database is accessible
check_database_health() {
    echo "🔍 Checking database connectivity..."
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
    echo "❌ Database migration failed"
    exit 1
fi

# Initialize database (safe - only creates data if tables are empty)
echo "📦 Initializing database schema and default data..."
echo "ℹ️  Note: init_db() is safe - it only creates tables (IF NOT EXISTS) and default tenant (if no tenants exist)"
if ! python -c "from src.core.database.database import init_db; init_db(exit_on_error=True)"; then
    echo "❌ Database initialization failed"
    exit 1
fi

# Start all services (MCP, Admin UI, ADK, nginx)
echo "🌐 Starting all services with unified routing..."
exec python scripts/deploy/run_all_services.py
