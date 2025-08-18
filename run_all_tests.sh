#!/bin/bash
# Test runner script for pre-push hook and manual testing

set -e  # Exit on first error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if we're in quick mode
MODE="${1:-full}"

echo -e "${GREEN}Running test suite in $MODE mode...${NC}"
echo ""

# Function to run tests
run_tests() {
    local test_path="$1"
    local test_name="$2"

    echo -e "${YELLOW}Running $test_name...${NC}"

    if [ "$MODE" = "quick" ]; then
        # Quick mode: only unit tests, fail fast
        uv run pytest "$test_path" -x --tb=short -q
    else
        # Full mode: all tests with verbose output
        uv run pytest "$test_path" -v --tb=short
    fi

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ $test_name passed${NC}"
        return 0
    else
        echo -e "${RED}❌ $test_name failed${NC}"
        return 1
    fi
}

# Track overall success
OVERALL_SUCCESS=0

# Run tests based on mode
if [ "$MODE" = "quick" ]; then
    echo "Quick mode: Running unit tests only..."
    echo ""

    # Run only unit tests for quick feedback
    run_tests "tests/unit/" "Unit tests" || OVERALL_SUCCESS=1

elif [ "$MODE" = "integration" ]; then
    echo "Integration mode: Running integration tests only..."
    echo ""

    # Run only integration tests
    run_tests "tests/integration/" "Integration tests" || OVERALL_SUCCESS=1

else
    echo "Full mode: Running all tests..."
    echo ""

    # Run all test categories
    run_tests "tests/unit/" "Unit tests" || OVERALL_SUCCESS=1
    echo ""
    run_tests "tests/integration/" "Integration tests" || OVERALL_SUCCESS=1
    echo ""
    run_tests "tests/e2e/" "End-to-end tests" || OVERALL_SUCCESS=1
fi

echo ""
echo "========================================="

if [ $OVERALL_SUCCESS -eq 0 ]; then
    echo -e "${GREEN}✅ All tests passed!${NC}"
    echo "========================================="
    exit 0
else
    echo -e "${RED}❌ Some tests failed!${NC}"
    echo ""
    echo "To run specific test categories:"
    echo "  ./run_all_tests.sh quick       # Unit tests only (fast)"
    echo "  ./run_all_tests.sh integration # Integration tests only"
    echo "  ./run_all_tests.sh             # All tests (default)"
    echo ""
    echo "To debug specific test:"
    echo "  uv run pytest tests/path/to/test.py -xvs"
    echo "========================================="
    exit 1
fi
