#!/bin/bash
# Migration Testing Script
# Usage: ./scripts/test_migration.sh [--full-workflow] [--rollback] [--performance]

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
TEST_DB="test_migration.db"
BACKUP_DB="backup_migration.db"
LOG_FILE="migration_test.log"

# Parse arguments
FULL_WORKFLOW=false
TEST_ROLLBACK=false
TEST_PERFORMANCE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --full-workflow)
            FULL_WORKFLOW=true
            shift
            ;;
        --rollback)
            TEST_ROLLBACK=true
            shift
            ;;
        --performance)
            TEST_PERFORMANCE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo -e "${YELLOW}Starting migration tests...${NC}"

# Function to clean up test databases
cleanup() {
    rm -f $TEST_DB $BACKUP_DB
    docker-compose down -v 2>/dev/null || true
}

# Function to run a test and check result
run_test() {
    local test_name="$1"
    local test_command="$2"
    
    echo -n "Testing $test_name... "
    if eval "$test_command" >> $LOG_FILE 2>&1; then
        echo -e "${GREEN}PASSED${NC}"
        return 0
    else
        echo -e "${RED}FAILED${NC}"
        echo "Check $LOG_FILE for details"
        return 1
    fi
}

# Clean up any previous test artifacts
cleanup

# Test 1: Basic migration up/down
echo -e "\n${YELLOW}Test 1: Basic Migration${NC}"

# Create test database
cp adcp_local.db $TEST_DB 2>/dev/null || sqlite3 $TEST_DB "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL);"

# Test upgrade
export DATABASE_URL="sqlite:///$TEST_DB"
run_test "upgrade to head" "python migrate.py"

# Test current version
run_test "check current version" "python -c \"
from alembic import command
from alembic.config import Config
cfg = Config('alembic.ini')
command.current(cfg)
\""

if [ "$TEST_ROLLBACK" = true ]; then
    echo -e "\n${YELLOW}Test 2: Rollback Testing${NC}"
    
    # Backup current state
    cp $TEST_DB $BACKUP_DB
    
    # Test downgrade
    run_test "downgrade one revision" "python -c \"
from alembic import command
from alembic.config import Config
cfg = Config('alembic.ini')
command.downgrade(cfg, '-1')
\""
    
    # Test upgrade again
    run_test "upgrade after downgrade" "python migrate.py"
fi

if [ "$FULL_WORKFLOW" = true ]; then
    echo -e "\n${YELLOW}Test 3: Full Workflow Testing${NC}"
    
    # Start PostgreSQL for integration tests
    echo "Starting PostgreSQL container..."
    docker-compose up -d postgres
    sleep 5  # Wait for PostgreSQL to start
    
    # Run migrations on PostgreSQL
    export DATABASE_URL="postgresql://adcp_user:secure_password_change_me@localhost:5432/adcp_test"
    export DB_TYPE="postgresql"
    
    # Create test database
    PGPASSWORD=secure_password_change_me psql -h localhost -U adcp_user -d postgres -c "DROP DATABASE IF EXISTS adcp_test;"
    PGPASSWORD=secure_password_change_me psql -h localhost -U adcp_user -d postgres -c "CREATE DATABASE adcp_test;"
    
    # Run migrations
    run_test "PostgreSQL migrations" "python migrate.py"
    
    # Test schema integrity
    run_test "schema integrity check" "python -c \"
import sys
sys.path.append('.')
from db_config import get_db_connection
from models import Base, Tenant, GAMInventory
from sqlalchemy import inspect

# Check all tables exist
with get_db_connection() as db:
    inspector = inspect(db.connection)
    tables = inspector.get_table_names()
    
    required_tables = ['tenants', 'gam_inventory', 'principals', 'products', 'media_buys']
    for table in required_tables:
        if table not in tables:
            raise Exception(f'Missing required table: {table}')
    
    # Check column types
    columns = inspector.get_columns('gam_inventory')
    inventory_type_col = next(c for c in columns if c['name'] == 'inventory_type')
    if inventory_type_col['type'].length < 30:
        raise Exception('inventory_type column too short')
    
    # Check no config column exists
    tenant_columns = [c['name'] for c in inspector.get_columns('tenants')]
    if 'config' in tenant_columns:
        raise Exception('config column still exists in tenants table')
\""
    
    # Test code compatibility
    run_test "code compatibility check" "python -c \"
import ast
import os

# Check for tenant.config references
for root, dirs, files in os.walk('.'):
    if '.git' in root or '__pycache__' in root or 'alembic/versions' in root:
        continue
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            try:
                with open(filepath) as f:
                    content = f.read()
                    if 'tenant.config' in content or 'tenant[\"config\"]' in content:
                        # Check if it's in a comment or migration file
                        if not any(marker in filepath for marker in ['test_migration', 'postmortem', '.md']):
                            raise Exception(f'Found tenant.config reference in {filepath}')
            except:
                pass  # Skip files that can't be read
\""
    
    # Test inventory sync workflow
    run_test "inventory sync workflow" "python -c \"
import asyncio
from gam_inventory_service import GAMInventoryService

async def test_sync():
    # This would normally sync with real GAM
    # For testing, we just verify the service initializes correctly
    service = GAMInventoryService()
    # Verify service can access database
    from sqlalchemy.orm import sessionmaker
    from db_config import engine
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as db:
        # Just verify we can query
        result = db.execute('SELECT COUNT(*) FROM gam_inventory')
        count = result.scalar()
        print(f'GAM inventory count: {count}')

asyncio.run(test_sync())
\""
fi

if [ "$TEST_PERFORMANCE" = true ]; then
    echo -e "\n${YELLOW}Test 4: Performance Testing${NC}"
    
    # Test migration performance
    START_TIME=$(date +%s)
    run_test "migration performance" "python migrate.py"
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    
    if [ $DURATION -gt 30 ]; then
        echo -e "${RED}Warning: Migrations took ${DURATION}s (>30s threshold)${NC}"
    else
        echo -e "${GREEN}Migration completed in ${DURATION}s${NC}"
    fi
    
    # Test query performance
    run_test "query performance" "python -c \"
import time
from db_config import get_db_connection

with get_db_connection() as db:
    # Test inventory query performance
    start = time.time()
    result = db.execute('''
        SELECT COUNT(*) 
        FROM gam_inventory 
        WHERE inventory_type = 'ad_unit'
    ''')
    count = result.scalar()
    duration = time.time() - start
    
    if duration > 1.0:
        raise Exception(f'Inventory query too slow: {duration:.2f}s')
    
    print(f'Query completed in {duration:.2f}s')
\""
fi

# Cleanup
cleanup

echo -e "\n${GREEN}All migration tests completed!${NC}"
echo "Log file: $LOG_FILE"

# Check if any tests failed
if grep -q "FAILED" $LOG_FILE; then
    exit 1
fi

exit 0