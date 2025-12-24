#!/bin/bash
set -e

echo "🚀 Starting AdCP Sales Agent..."

# Validate required environment variables
validate_required_env() {
    echo "🔍 Validating required environment variables..."

    local missing=()

    # Super admin access - at least one must be set
    if [ -z "$SUPER_ADMIN_EMAILS" ] && [ -z "$SUPER_ADMIN_DOMAINS" ]; then
        missing+=("SUPER_ADMIN_EMAILS or SUPER_ADMIN_DOMAINS")
    fi

    # Database URL is required
    if [ -z "$DATABASE_URL" ]; then
        missing+=("DATABASE_URL")
    fi

    if [ ${#missing[@]} -gt 0 ]; then
        echo "❌ Missing required environment variables:"
        for var in "${missing[@]}"; do
            echo "   - $var"
        done
        echo ""
        echo "📖 See docs/deployment.md for configuration details."
        echo ""
        echo "Quick fix for Fly.io:"
        echo "  fly secrets set SUPER_ADMIN_EMAILS=\"your-email@example.com\""
        echo ""
        exit 1
    fi

    echo "✅ Required environment variables are set"
}

# Validate required env vars first
validate_required_env

# Function to check if database is accessible
check_database_health() {
    echo "🔍 Checking database connectivity..."
    echo "Python path: $(which python)"
    echo "Python version: $(python --version)"
    echo "Checking if psycopg2 is available..."
    python -c "import psycopg2; print('✅ psycopg2 imported successfully')" || (echo "❌ psycopg2 not available"; exit 1)
    python -c "
from src.core.database.db_config import get_db_connection, DatabaseConfig
import os

# Show parsed connection info (without password)
db_url = os.environ.get('DATABASE_URL', '')
print(f'DATABASE_URL set: {bool(db_url)}')

if db_url:
    config = DatabaseConfig.get_db_config()
    print(f'Parsed host: {config.get(\"host\", \"NOT SET\")}')
    print(f'Parsed port: {config.get(\"port\", \"NOT SET\")}')
    print(f'Parsed database: {config.get(\"database\", \"NOT SET\")}')

try:
    conn = get_db_connection()
    cursor = conn.execute('SELECT 1')
    result = cursor.fetchone()
    conn.close()
    print('✅ Database connection successful')
except Exception as e:
    error_str = str(e)
    print(f'❌ Database connection failed: {e}')
    print('')

    # Provide specific guidance based on error
    if 'No such file or directory' in error_str and '/var/run/postgresql' in error_str:
        print('💡 This error means the DATABASE_URL is missing a host.')
        print('')
        print('   For Cloud Run with Cloud SQL, use one of these formats:')
        print('')
        print('   Option 1 - Public IP (simpler but less secure):')
        print('     DATABASE_URL=postgresql://USER:PASS@IP_ADDRESS:5432/DATABASE')
        print('     Example: postgresql://postgres:YOUR_PASSWORD@YOUR_IP:5432/postgres')
        print('')
        print('   Option 2 - Cloud SQL Connector (recommended):')
        print('     1. Add Cloud SQL connection in Cloud Run service settings')
        print('     2. Use: DATABASE_URL=postgresql://USER:PASS@/DATABASE?host=/cloudsql/PROJECT:REGION:INSTANCE')
        print('')
    elif 'could not connect to server' in error_str or 'Connection refused' in error_str:
        print('💡 Database server is unreachable. Check:')
        print('   - Is the IP address correct?')
        print('   - Is Cloud SQL instance running?')
        print('   - Are authorized networks configured? (Cloud SQL > Connections > Authorized networks)')
        print('')
    elif 'password authentication failed' in error_str:
        print('💡 Wrong password. Check:')
        print('   - Password in DATABASE_URL matches Cloud SQL user password')
        print('   - Special characters are URL-encoded (& -> %26, = -> %3D, etc.)')
        print('')
    elif 'database' in error_str and 'does not exist' in error_str:
        print('💡 Database does not exist. Either:')
        print('   - Use the default \"postgres\" database')
        print('   - Create your database: CREATE DATABASE yourdb;')
        print('')

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
