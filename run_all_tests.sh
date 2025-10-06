#!/bin/bash
# Test runner script for pre-push hook validation
# Implements the testing workflow documented in CLAUDE.md

set -e  # Exit on first error

# Get the directory of the script (works even when called from git hooks)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Determine test mode
MODE=${1:-full}  # Default to full if no argument

echo "🧪 Running tests in '$MODE' mode..."
echo ""

# Quick mode: unit tests + import validation
if [ "$MODE" == "quick" ]; then
    echo "📦 Step 1/2: Validating critical imports..."

    # Check if key imports work (catches missing imports early)
    if ! uv run python -c "from src.core.tools import get_products_raw, create_media_buy_raw" 2>/dev/null; then
        echo -e "${RED}❌ Import validation failed!${NC}"
        echo "One or more A2A raw functions cannot be imported."
        exit 1
    fi

    if ! uv run python -c "from src.core.main import _get_products_impl, _create_media_buy_impl" 2>/dev/null; then
        echo -e "${RED}❌ Import validation failed!${NC}"
        echo "One or more shared implementation functions cannot be imported."
        exit 1
    fi

    echo -e "${GREEN}✅ Imports validated${NC}"
    echo ""

    echo "🧪 Step 2/2: Running unit tests..."
    if ! uv run pytest tests/unit/ -x --tb=short; then
        echo -e "${RED}❌ Unit tests failed!${NC}"
        exit 1
    fi

    echo -e "${GREEN}✅ Quick tests passed${NC}"
    echo ""
    echo -e "${YELLOW}ℹ️  Note: Integration tests not run in quick mode${NC}"
    echo "   Run './run_all_tests.sh' for full validation"
    exit 0
fi

# Full mode: all tests
if [ "$MODE" == "full" ]; then
    echo "📦 Step 1/4: Validating imports..."

    # Check all critical imports
    if ! uv run python -c "from src.core.tools import get_products_raw, create_media_buy_raw, get_media_buy_delivery_raw, sync_creatives_raw, list_creatives_raw, list_creative_formats_raw, list_authorized_properties_raw" 2>/dev/null; then
        echo -e "${RED}❌ Import validation failed!${NC}"
        exit 1
    fi

    if ! uv run python -c "from src.core.main import _get_products_impl, _create_media_buy_impl, _get_media_buy_delivery_impl, _sync_creatives_impl, _list_creatives_impl, _list_creative_formats_impl, _list_authorized_properties_impl" 2>/dev/null; then
        echo -e "${RED}❌ Import validation failed!${NC}"
        exit 1
    fi

    echo -e "${GREEN}✅ Imports validated${NC}"
    echo ""

    echo "🧪 Step 2/4: Running unit tests..."
    if ! uv run pytest tests/unit/ -x --tb=short; then
        echo -e "${RED}❌ Unit tests failed!${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ Unit tests passed${NC}"
    echo ""

    echo "🔗 Step 3/4: Running integration tests..."
    if ! uv run pytest tests/integration/ -x --tb=short; then
        echo -e "${RED}❌ Integration tests failed!${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ Integration tests passed${NC}"
    echo ""

    echo "🌍 Step 4/4: Running e2e tests..."
    if ! uv run pytest tests/e2e/ -x --tb=short; then
        echo -e "${RED}❌ E2E tests failed!${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ E2E tests passed${NC}"
    echo ""

    echo -e "${GREEN}✅ All tests passed!${NC}"
    exit 0
fi

# Unknown mode
echo -e "${RED}❌ Unknown test mode: $MODE${NC}"
echo "Usage: ./run_all_tests.sh [quick|full]"
echo "  quick: unit tests + import validation (fast, for pre-push)"
echo "  full:  all tests including integration and e2e (comprehensive)"
exit 1
