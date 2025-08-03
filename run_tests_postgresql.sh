#!/bin/bash
# Run tests with PostgreSQL to match CI environment

echo "🧪 Running tests with PostgreSQL (matching CI environment)"
echo "=========================================================="

# Use the existing PostgreSQL from docker-compose
export DATABASE_URL="postgresql://adcp_user:secure_password_change_me@localhost:5521/adcp"
export DB_TYPE="postgresql"

# Set other required environment variables
export GEMINI_API_KEY="test_key_for_mocking"
export GOOGLE_CLIENT_ID="test_client_id"
export GOOGLE_CLIENT_SECRET="test_client_secret"
export SUPER_ADMIN_EMAILS="test@example.com"
export CI="true"

echo "Environment:"
echo "  DATABASE_URL: $DATABASE_URL"
echo "  DB_TYPE: $DB_TYPE"
echo ""

# Initialize database (like CI does)
echo "1️⃣ Initializing test database..."
uv run python init_database_ci.py
if [ $? -ne 0 ]; then
    echo "❌ Database initialization failed!"
    exit 1
fi

echo ""
echo "2️⃣ Running unit tests..."
uv run pytest tests/unit/test_admin_ui_oauth.py tests/test_adapters.py test_adapter_targeting.py test_creative_format_parsing.py -v --tb=short

echo ""
echo "3️⃣ Running integration tests..."
uv run pytest test_main.py test_admin_creative_approval.py test_creative_auto_approval.py test_human_task_queue.py -v --tb=short

echo ""
echo "4️⃣ Running AI tests..."
uv run pytest test_ai_product_basic.py -v --tb=short

echo ""
echo "✅ Done! These results should match what CI sees."