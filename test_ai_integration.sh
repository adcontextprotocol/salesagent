#!/bin/bash
# Integration test script for AI product features
# Run this inside the Docker container or with proper environment setup

set -e

echo "=== AdCP AI Product Features Integration Test ==="
echo

# Check environment
echo "1. Checking environment variables..."
if [ -z "$GEMINI_API_KEY" ]; then
    echo "⚠️  WARNING: GEMINI_API_KEY not set - AI features will use mocks"
else
    echo "✅ GEMINI_API_KEY is set"
fi

if [ -z "$DATABASE_URL" ]; then
    echo "⚠️  WARNING: DATABASE_URL not set - using default"
    export DATABASE_URL="sqlite:///test_integration.db"
fi

echo "✅ DATABASE_URL: ${DATABASE_URL:0:30}..."
echo

# Test 1: Create a tenant with default products
echo "2. Testing tenant creation with default products..."
python3 setup_tenant.py "Test AI Publisher" \
    --tenant-id test_ai_tenant \
    --adapter mock \
    --industry news \
    2>&1 | grep -E "(Created|default products|✅)" || echo "❌ Failed to create tenant"

echo

# Test 2: Test product templates API
echo "3. Testing product suggestions API..."
python3 -c "
import requests
from admin_ui import app

# Create test client
app.config['TESTING'] = True
with app.test_client() as client:
    # Mock session
    with client.session_transaction() as sess:
        sess['email'] = 'test@example.com'
        sess['role'] = 'super_admin'
    
    # Test suggestions endpoint
    response = client.get('/api/tenant/test_ai_tenant/products/suggestions?industry=news')
    if response.status_code == 200:
        data = response.json
        print(f'✅ API returned {data[\"total_count\"]} product suggestions')
        if data['suggestions']:
            print(f'   Sample: {data[\"suggestions\"][0][\"name\"]}')
    else:
        print(f'❌ API failed with status {response.status_code}')
"

echo

# Test 3: Test AI product configuration (if API key available)
if [ ! -z "$GEMINI_API_KEY" ] && [ "$GEMINI_API_KEY" != "test_key_for_mocking" ]; then
    echo "4. Testing AI product configuration..."
    python3 -c "
import asyncio
from ai_product_service import AIProductConfigurationService

async def test():
    try:
        service = AIProductConfigurationService()
        print(f'✅ AI service initialized with model: {service.model._model_name}')
        
        # Quick test
        response = service.model.generate_content('Return JSON: {\"status\": \"ok\"}')
        print('✅ AI model responded successfully')
    except Exception as e:
        print(f'❌ AI test failed: {e}')

asyncio.run(test())
"
else
    echo "4. Skipping live AI test (no API key)"
fi

echo

# Test 4: Verify default products were created
echo "5. Verifying default products..."
python3 -c "
from db_config import get_db_connection
import json

conn = get_db_connection()
cursor = conn.execute(
    'SELECT COUNT(*) FROM products WHERE tenant_id = ?',
    ('test_ai_tenant',)
)
count = cursor.fetchone()[0]
print(f'✅ Found {count} products for test tenant')

# Show sample products
cursor = conn.execute(
    'SELECT product_id, name, delivery_type FROM products WHERE tenant_id = ? LIMIT 3',
    ('test_ai_tenant',)
)
for row in cursor:
    print(f'   - {row[0]}: {row[1]} ({row[2]})')

conn.close()
"

echo
echo "=== Integration test complete ==="