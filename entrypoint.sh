#!/bin/bash
set -e

echo "🚀 Starting AdCP Sales Agent..."

# Function to check if database is accessible
check_database_health() {
    echo "🔍 Checking database connectivity..."
    python -c "
from db_config import get_db_connection
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
if ! python migrate.py; then
    echo "❌ Database migration failed"
    exit 1
fi

# Initialize database (safe - only creates data if tables are empty)
echo "📦 Initializing database schema and default data..."
echo "ℹ️  Note: init_db() is safe - it only creates tables (IF NOT EXISTS) and default tenant (if no tenants exist)"
if ! python -c "from database import init_db; init_db()"; then
    echo "❌ Database initialization failed"
    exit 1
fi

# Start both servers
echo "🌐 Starting servers..."
exec bash debug_start.sh