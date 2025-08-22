#\!/bin/bash
# Test with real authentication flow

echo "Testing settings page with real auth..."

# Get cookies from test auth
COOKIES=$(curl -s -c - -X POST http://localhost:8004/test/auth \
  -H "Content-Type: application/json" \
  -d '{"email":"test_super_admin@example.com","password":"test123","tenant_id":""}' \
  | grep session | awk '{print $7}')

echo "Session cookie: $COOKIES"

# Test settings page with real session
echo "Testing /tenant/default/settings..."
RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
  -H "Cookie: session=$COOKIES" \
  http://localhost:8004/tenant/default/settings)

HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
echo "Response code: $HTTP_CODE"

if [ "$HTTP_CODE" = "500" ]; then
  echo "ERROR: Still getting 500\!"
  echo "$RESPONSE" | head -100
  exit 1
elif [ "$HTTP_CODE" = "200" ]; then
  echo "SUCCESS: Settings page loads\!"
  exit 0
else
  echo "Got status code: $HTTP_CODE"
  exit 1
fi
