#!/bin/bash
# Script to demonstrate test authentication mode

echo "AdCP Admin UI - Test Authentication Mode Demo"
echo "============================================="
echo ""

# Step 1: Set up environment
echo "1. Setting up test environment..."
export ADCP_AUTH_TEST_MODE=true
export GEMINI_API_KEY=${GEMINI_API_KEY:-"test-key-for-demo"}
export SUPER_ADMIN_EMAILS="test_super_admin@example.com"

# Create a temporary .env file for docker-compose
cat > .env.test << EOF
ADCP_AUTH_TEST_MODE=true
GEMINI_API_KEY=${GEMINI_API_KEY}
SUPER_ADMIN_EMAILS=test_super_admin@example.com
GOOGLE_CLIENT_ID=test-client-id
GOOGLE_CLIENT_SECRET=test-client-secret
POSTGRES_PORT=5437
ADCP_SALES_PORT=8084
ADMIN_UI_PORT=8005
FLASK_DEBUG=0
EOF

echo "   ✅ Environment configured with test mode enabled"
echo ""

# Step 2: Start services
echo "2. Starting services with test mode..."
docker compose --env-file .env.test up -d

echo "   Waiting for services to be ready..."
sleep 10

# Check if services are healthy
echo ""
echo "3. Checking service status..."
docker compose ps

echo ""
echo "   Waiting a bit more for full initialization..."
sleep 5

# Step 4: Run the test
echo ""
echo "4. Running authentication test..."
echo "================================="
echo ""

# Make sure we have requests installed
uv add requests >/dev/null 2>&1 || true

# Run the test with environment variable set
ADCP_AUTH_TEST_MODE=true ADMIN_UI_PORT=8005 uv run python test_ui_auth_simple_fixed.py

# Capture exit code
TEST_EXIT_CODE=$?

echo ""
echo "5. Test completed!"
echo ""

# Step 5: Show logs if test failed
if [ $TEST_EXIT_CODE -ne 0 ]; then
    echo "❌ Test failed! Showing recent logs..."
    echo ""
    echo "Admin UI logs:"
    docker compose logs --tail=20 admin-ui
fi

# Step 6: Cleanup prompt
echo ""
echo "6. Cleanup"
echo "=========="
echo ""
echo "Services are still running. You can:"
echo "  - Visit http://localhost:8005/test/login to try the test login"
echo "  - Visit http://localhost:8005/login to see the normal login with test mode"
echo ""
echo "To stop services: docker compose down"
echo "To remove test env: rm .env.test"
echo ""

# Return the test exit code
exit $TEST_EXIT_CODE