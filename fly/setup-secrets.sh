#!/bin/bash
# Setup Fly.io secrets for AdCP Sales Agent

echo "Setting up Fly.io secrets for AdCP Sales Agent..."

# Required secrets
fly secrets set GEMINI_API_KEY="${GEMINI_API_KEY}"
fly secrets set GOOGLE_CLIENT_ID="${GOOGLE_CLIENT_ID}"
fly secrets set GOOGLE_CLIENT_SECRET="${GOOGLE_CLIENT_SECRET}"
fly secrets set SUPER_ADMIN_EMAILS="${SUPER_ADMIN_EMAILS}"
fly secrets set SUPER_ADMIN_DOMAINS="${SUPER_ADMIN_DOMAINS}"

# Database URL (will be set after PostgreSQL is created)
# fly secrets set DATABASE_URL="postgresql://..."

# Optional secrets
if [ ! -z "$SLACK_WEBHOOK_URL" ]; then
    fly secrets set SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL}"
fi

echo "Secrets configuration complete!"
echo ""
echo "Next steps:"
echo "1. Create PostgreSQL database: fly postgres create --name adcp-db"
echo "2. Attach database: fly postgres attach adcp-db"
echo "3. The DATABASE_URL will be automatically set"
echo "4. Deploy: fly deploy"