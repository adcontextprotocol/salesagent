#!/bin/bash
# Unified test runner for AdCP Sales Agent
# This script runs all tests and can be used locally or in CI/CD

set -e  # Exit on error

echo "========================================="
echo "AdCP Sales Agent - Unified Test Suite"
echo "========================================="

# Function to print colored output
print_status() {
    if [ "$2" = "success" ]; then
        echo -e "\033[0;32m✓ $1\033[0m"
    elif [ "$2" = "error" ]; then
        echo -e "\033[0;31m✗ $1\033[0m"
    else
        echo -e "\033[0;33m→ $1\033[0m"
    fi
}

# Check if we're in CI environment
if [ "$CI" = "true" ]; then
    print_status "Running in CI environment" "info"
else
    print_status "Running in local environment" "info"
fi

# Create/activate virtual environment if needed
if [ ! -d "test_venv" ] && [ "$CI" != "true" ]; then
    print_status "Creating virtual environment..." "info"
    python3 -m venv test_venv
fi

if [ -d "test_venv" ] && [ "$CI" != "true" ]; then
    print_status "Activating virtual environment..." "info"
    source test_venv/bin/activate
fi

# Install dependencies
print_status "Installing test dependencies..." "info"
pip install -q pytest pytest-mock pytest-cov

# Install project dependencies needed for tests
print_status "Installing project dependencies..." "info"
pip install -q pydantic sqlalchemy psycopg2-binary flask authlib requests fastmcp
pip install -q google-generativeai rich google-ads googleads
pip install -q beautifulsoup4 aiohttp alembic watchdog
pip install -q fastapi uvicorn requests-oauthlib

# Set test environment
export ADCP_TESTING=true
export DATABASE_URL=sqlite:///test.db

# Run tests based on mode
MODE=${1:-"standard"}
FAILED_TESTS=0

case $MODE in
    "quick")
        print_status "Running quick test check..." "info"
        pytest -q || FAILED_TESTS=$?
        ;;
    "coverage")
        print_status "Running tests with coverage..." "info"
        pytest --cov=. --cov-report=term-missing --cov-report=html \
               --cov-config=.coveragerc || FAILED_TESTS=$?
        if [ $FAILED_TESTS -eq 0 ]; then
            print_status "Coverage report generated in htmlcov/" "success"
        fi
        ;;
    "verbose")
        print_status "Running tests in verbose mode..." "info"
        pytest -v -s || FAILED_TESTS=$?
        ;;
    "ci")
        print_status "Running tests for CI..." "info"
        pytest --tb=short --strict-markers -v \
               --junitxml=test-results.xml \
               --cov=. --cov-report=xml --cov-report=term || FAILED_TESTS=$?
        ;;
    *)
        print_status "Running standard tests..." "info"
        pytest -v || FAILED_TESTS=$?
        ;;
esac

# Summary
echo ""
echo "========================================="
if [ $FAILED_TESTS -eq 0 ]; then
    print_status "All tests passed!" "success"
    echo ""
    echo "Test files run:"
    find . -name "test_*.py" -not -path "./test_venv/*" -type f | sort | while read f; do
        echo "  - $f"
    done
else
    print_status "Tests failed with exit code: $FAILED_TESTS" "error"
    echo ""
    echo "Run with 'verbose' mode for more details:"
    echo "  ./run_all_tests.sh verbose"
fi
echo "========================================="

# Exit with the same code as pytest
exit $FAILED_TESTS