#!/bin/bash
# Set secrets for AdCP Sales Agent on Fly.io

echo "Setting required secrets for AdCP Sales Agent..."

# Set required secrets with placeholder values
# You'll need to update these with your actual values

fly secrets set \
  GEMINI_API_KEY="your-gemini-api-key-here" \
  GOOGLE_CLIENT_ID="your-client-id.apps.googleusercontent.com" \
  GOOGLE_CLIENT_SECRET="your-client-secret" \
  SUPER_ADMIN_EMAILS="admin@example.com" \
  SUPER_ADMIN_DOMAINS="example.com" \
  --app adcp-sales-agent

echo "Secrets set! Please update them with your actual values."
echo ""
echo "To update individual secrets:"
echo "  fly secrets set GEMINI_API_KEY=your-actual-key --app adcp-sales-agent"
echo ""
echo "Current secrets:"
fly secrets list --app adcp-sales-agent
