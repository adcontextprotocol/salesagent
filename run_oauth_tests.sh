#!/bin/bash
# Script to run OAuth tests for the Admin UI

echo "Running Admin UI OAuth Tests"
echo "==========================="

# Check if virtual environment exists
if [ -d "test_venv" ]; then
    echo "Activating test_venv..."
    source test_venv/bin/activate
fi

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo "Error: pytest is not installed"
    echo "Please install it with: pip install pytest pytest-mock"
    exit 1
fi

# Run tests with different verbosity levels based on argument
if [ "$1" = "verbose" ]; then
    echo "Running in verbose mode..."
    pytest test_admin_ui_oauth.py -v -s
elif [ "$1" = "coverage" ]; then
    echo "Running with coverage report..."
    pytest test_admin_ui_oauth.py --cov=admin_ui --cov-report=html --cov-report=term
elif [ "$1" = "quick" ]; then
    echo "Running quick test summary..."
    pytest test_admin_ui_oauth.py -q
else
    echo "Running standard tests..."
    pytest test_admin_ui_oauth.py -v
fi

echo ""
echo "Test run complete!"
echo ""
echo "Usage:"
echo "  ./run_oauth_tests.sh          # Run with standard verbosity"
echo "  ./run_oauth_tests.sh verbose  # Run with full output"
echo "  ./run_oauth_tests.sh coverage # Run with coverage report"
echo "  ./run_oauth_tests.sh quick    # Run with minimal output"