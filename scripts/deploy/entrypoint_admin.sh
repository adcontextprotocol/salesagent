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

# Debug: Check Python environment
echo "🔍 Debugging Python environment..."
echo "Python location: $(which python)"
echo "Python version: $(python --version)"
python -c "import sys; print('Python executable:', sys.executable)"
python -c "import sys; print('sys.path:', sys.path)"

# Debug: Check if flask_caching is importable
echo "🔍 Checking flask_caching availability..."
python -c "import flask_caching; print('✅ flask_caching version:', flask_caching.__version__)" || echo "❌ flask_caching import failed"

# Start the admin UI
echo "🌐 Starting Admin UI..."
exec python -m src.admin.server
