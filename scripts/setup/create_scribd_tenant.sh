#!/bin/bash
# Create a Scribd tenant for testing

echo "Creating Scribd tenant..."

docker-compose exec adcp-server python setup_tenant.py "Scribd" \
  --subdomain scribd \
  --adapter google_ad_manager \
  --gam-network-code 22797863291 \
  --industry publishing

echo ""
echo "To configure GAM for Scribd:"
echo "1. Visit http://localhost:8001"
echo "2. Login as super admin"
echo "3. Click on 'Scribd' tenant"
echo "4. Go to 'Ad Server Setup'"
echo "5. Complete the OAuth flow"
echo ""
echo "Or use the mock adapter instead:"
echo "docker-compose exec adcp-server python setup_tenant.py 'Scribd' --subdomain scribd --adapter mock"
