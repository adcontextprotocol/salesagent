#!/bin/bash
# Run the Claude UI Testing Subagent

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}🤖 Claude UI Testing Subagent${NC}"
echo -e "${BLUE}================================${NC}"

# Check if we're in the right directory
if [ ! -f "ui_test_server.py" ]; then
    echo -e "${YELLOW}Error: Must run from claude_subagent directory${NC}"
    exit 1
fi

# Set environment variables
export PYTHONPATH="../.."
export BASE_URL="${BASE_URL:-http://localhost:${ADMIN_UI_PORT:-8001}}"
export HEADLESS="${HEADLESS:-true}"

echo -e "${GREEN}✓ Environment configured${NC}"
echo "  PYTHONPATH: $PYTHONPATH"
echo "  BASE_URL: $BASE_URL"
echo "  HEADLESS: $HEADLESS"
echo ""

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo -e "${YELLOW}Error: uv is not installed${NC}"
    echo "Please install uv first"
    exit 1
fi

# Check dependencies
echo -e "${BLUE}Checking dependencies...${NC}"
cd ../..
uv sync --extra ui-tests
cd ui_tests/claude_subagent

echo -e "${GREEN}✓ Dependencies ready${NC}"
echo ""

# Start the server
echo -e "${BLUE}Starting MCP server on port 8090...${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
echo ""

uv run python ui_test_server.py