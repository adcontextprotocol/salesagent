#!/bin/bash
# Deploy delivery_type migration fix to production
# Run this script to deploy the f9300bf2246d migration to fix validation errors

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}🔧 Delivery Type Migration Deployment${NC}"
echo "=========================================="
echo ""

# Check if app name provided
if [ -z "$1" ]; then
    echo -e "${RED}❌ Error: App name required${NC}"
    echo "Usage: $0 <app-name>"
    echo "Example: $0 wonderstruck-sales-agent"
    echo ""
    echo "Available apps:"
    echo "  - wonderstruck-sales-agent"
    echo "  - test-agent"
    exit 1
fi

APP_NAME="$1"

echo -e "${YELLOW}📱 Target App: ${APP_NAME}${NC}"
echo ""

# Step 1: Check current migration state
echo -e "${YELLOW}Step 1: Checking current migration state...${NC}"
fly ssh console --app "$APP_NAME" --command "cd /app && uv run alembic current"
echo ""

# Step 2: Run migrations
echo -e "${YELLOW}Step 2: Running pending migrations...${NC}"
fly ssh console --app "$APP_NAME" --command "cd /app && uv run python migrate.py"
echo ""

# Step 3: Verify migration applied
echo -e "${YELLOW}Step 3: Verifying migration applied...${NC}"
fly ssh console --app "$APP_NAME" --command "cd /app && uv run alembic current"
echo ""

# Step 4: Check data integrity
echo -e "${YELLOW}Step 4: Checking data integrity...${NC}"
fly ssh console --app "$APP_NAME" --command "cd /app && uv run python -c \"
from src.core.database.database_session import get_db_session
from src.core.database.models import Product
from sqlalchemy import select

with get_db_session() as session:
    # Check for old format
    stmt = select(Product).where(Product.delivery_type == 'non-guaranteed')
    bad_products = session.scalars(stmt).all()

    # Check for new format
    stmt = select(Product).where(Product.delivery_type == 'non_guaranteed')
    good_products = session.scalars(stmt).all()

    print(f'✅ Products with old format (should be 0): {len(bad_products)}')
    print(f'✅ Products with new format: {len(good_products)}')

    if len(bad_products) > 0:
        print('❌ ERROR: Still have products with old format!')
        exit(1)
    else:
        print('✅ SUCCESS: All products use correct format')
\""
echo ""

echo -e "${GREEN}✅ Deployment Complete!${NC}"
echo ""
echo "Next steps:"
echo "  1. Test get_products endpoint manually"
echo "  2. Run full integration tests"
echo "  3. Monitor for validation errors"
echo ""
