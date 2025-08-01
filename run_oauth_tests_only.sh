#!/bin/bash
# Focused test runner for OAuth tests only
# Use this until the full test suite import issues are resolved

set -e

echo "========================================="
echo "Running OAuth Tests Only"
echo "========================================="

# Check/create virtual environment
if [ ! -d "test_venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv test_venv
fi

# Activate virtual environment
source test_venv/bin/activate

# Install minimal dependencies
echo "Installing dependencies..."
pip install -q pytest pytest-mock pytest-cov
pip install -q pydantic sqlalchemy psycopg2-binary flask authlib requests fastmcp

# Run OAuth tests
echo "Running OAuth tests..."
pytest tests/unit/test_admin_ui_oauth.py -v

echo ""
echo "========================================="
echo "✅ OAuth tests completed!"
echo "========================================="