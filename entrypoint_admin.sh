#!/bin/bash
set -e

echo "🚀 Starting AdCP Admin UI..."

# Wait for database to be ready
echo "⏳ Waiting for database..."
for i in {1..30}; do
    if python -c "import psycopg2; psycopg2.connect('${DATABASE_URL}')" 2>/dev/null; then
        echo "✅ Database is ready!"
        break
    fi
    echo "Waiting for database... ($i/30)"
    sleep 2
done

# Run database migrations
echo "📦 Running database migrations..."
python migrate.py

# Start the admin UI
echo "🌐 Starting Admin UI..."
exec python admin_ui.py