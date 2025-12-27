#!/bin/bash
# setup_conductor_workspace.sh - Automated setup for Conductor workspaces

# Add .venv/bin to PATH if it exists and not already added
if [ -d ".venv/bin" ] && [[ ":$PATH:" != *":.venv/bin:"* ]]; then
    export PATH="$(pwd)/.venv/bin:$PATH"
    echo "✓ Added .venv/bin to PATH for this session"
fi

# Check if Conductor environment variables are set
if [ -z "$CONDUCTOR_WORKSPACE_NAME" ]; then
    echo "Error: This script should be run within a Conductor workspace"
    echo "CONDUCTOR_WORKSPACE_NAME is not set"
    exit 1
fi

echo "Setting up Conductor workspace: $CONDUCTOR_WORKSPACE_NAME"
echo "Workspace path: $CONDUCTOR_WORKSPACE_PATH"
echo "Root path: $CONDUCTOR_ROOT_PATH"

# Check and install uv if needed
echo ""
echo "Checking for uv package manager..."
if ! command -v uv &> /dev/null; then
    echo "✗ uv not found, installing via Homebrew..."
    if command -v brew &> /dev/null; then
        brew install uv
        if command -v uv &> /dev/null; then
            echo "✓ uv installed successfully"
        else
            echo "✗ Warning: uv installation failed"
            echo "  Schema generation will be skipped"
            echo "  To install manually: brew install uv"
        fi
    else
        echo "✗ Warning: Homebrew not found, cannot auto-install uv"
        echo "  To install uv manually:"
        echo "    macOS: brew install uv"
        echo "    Linux: curl -LsSf https://astral.sh/uv/install.sh | sh"
        echo "  Schema generation will be skipped"
    fi
else
    echo "✓ uv is already installed ($(uv --version))"
fi

# Check for .env file
echo ""
echo "Checking environment configuration..."

if [ -f ".env" ]; then
    echo "✓ Found .env in current directory"
elif [ -f "$CONDUCTOR_ROOT_PATH/.env" ]; then
    cp "$CONDUCTOR_ROOT_PATH/.env" .env
    echo "✓ Copied .env from root directory ($CONDUCTOR_ROOT_PATH)"
else
    echo "✗ ERROR: .env file not found!"
    echo ""
    echo "Please create $CONDUCTOR_ROOT_PATH/.env with your configuration:"
    echo ""
    echo "# API Keys"
    echo "GEMINI_API_KEY=your-gemini-api-key"
    echo ""
    echo "# OAuth Configuration"
    echo "GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com"
    echo "GOOGLE_CLIENT_SECRET=your-client-secret"
    echo "SUPER_ADMIN_EMAILS=your-email@example.com"
    echo ""
    echo "# GAM OAuth (optional - only needed for Google Ad Manager)"
    echo "GAM_OAUTH_CLIENT_ID=your-gam-client-id.apps.googleusercontent.com"
    echo "GAM_OAUTH_CLIENT_SECRET=your-gam-client-secret"
    echo ""
    echo "See .env.template for a full example."
    echo ""
    exit 1
fi

# Set up Docker caching infrastructure
echo ""
echo "Setting up Docker caching..."

# Create shared cache volumes if they don't exist
if docker volume inspect adcp_global_pip_cache >/dev/null 2>&1; then
    echo "✓ Docker pip cache volume already exists"
else
    docker volume create adcp_global_pip_cache >/dev/null
    echo "✓ Created shared pip cache volume"
fi

if docker volume inspect adcp_global_uv_cache >/dev/null 2>&1; then
    echo "✓ Docker uv cache volume already exists"
else
    docker volume create adcp_global_uv_cache >/dev/null
    echo "✓ Created shared uv cache volume"
fi

# Copy required files from root workspace
echo ""
echo "Copying files from root workspace..."
if [ -f "$CONDUCTOR_ROOT_PATH/adcp-manager-key.json" ]; then
    cp "$CONDUCTOR_ROOT_PATH/adcp-manager-key.json" .
    echo "✓ Copied adcp-manager-key.json"
fi

# Set up Git hooks for this workspace
echo ""
echo "Setting up Git hooks..."

# Configure git to use worktree-specific hooks
echo "Configuring worktree-specific hooks..."

# Enable worktree config
git config extensions.worktreeconfig true

# Get the worktree's git directory
WORKTREE_GIT_DIR=$(git rev-parse --git-dir)
WORKTREE_HOOKS_DIR="$WORKTREE_GIT_DIR/hooks"
MAIN_HOOKS_DIR="$(git rev-parse --git-common-dir)/hooks"

# Create hooks directory if it doesn't exist
mkdir -p "$WORKTREE_HOOKS_DIR"

# Configure this worktree to use its own hooks directory
git config --worktree core.hooksPath "$WORKTREE_HOOKS_DIR"
echo "✓ Configured worktree to use hooks at: $WORKTREE_HOOKS_DIR"

# Install pre-commit if available
if command -v pre-commit &> /dev/null && [ -f .pre-commit-config.yaml ]; then
    echo "Installing pre-commit hooks..."

    # Pre-commit doesn't like custom hooks paths, so temporarily unset it
    git config --worktree --unset core.hooksPath 2>/dev/null
    pre-commit install >/dev/null 2>&1
    PRECOMMIT_RESULT=$?

    # Copy the pre-commit hook to our worktree hooks directory
    if [ $PRECOMMIT_RESULT -eq 0 ] && [ -f "$MAIN_HOOKS_DIR/pre-commit" ]; then
        cp "$MAIN_HOOKS_DIR/pre-commit" "$WORKTREE_HOOKS_DIR/pre-commit"
        echo "✓ Pre-commit hooks installed in worktree"
    else
        echo "✗ Warning: Failed to install pre-commit hooks"
        echo "  To install manually, run: pre-commit install"
    fi

    # Restore the worktree hooks path
    git config --worktree core.hooksPath "$WORKTREE_HOOKS_DIR"
else
    echo "✗ Warning: pre-commit not found or config missing"
    echo "  To install pre-commit: pip install pre-commit"
    echo "  Then run: pre-commit install"
fi

# Set up pre-push hook
if [ -f run_all_tests.sh ]; then
    echo "✓ Test runner script found (./run_all_tests.sh)"

    # Create/update pre-push hook
    cat > "$WORKTREE_HOOKS_DIR/pre-push" << 'EOF'
#!/bin/bash
# Pre-push hook that works correctly with git worktrees
# This hook runs tests before allowing a push to remote

echo "Running tests before push..."

# Get the actual working directory (handles both regular repos and worktrees)
WORK_DIR="$(git rev-parse --show-toplevel)"
cd "$WORK_DIR"

echo "Working directory: $WORK_DIR"

# Check if test runner exists in the worktree
if [ -f "./run_all_tests.sh" ]; then
    # Run quick tests
    ./run_all_tests.sh quick
    TEST_RESULT=$?

    if [ $TEST_RESULT -ne 0 ]; then
        echo ""
        echo "❌ Tests failed! Push aborted."
        echo ""
        echo "To run full test suite:"
        echo "  ./run_all_tests.sh"
        echo ""
        echo "To push anyway (not recommended):"
        echo "  git push --no-verify"
        echo ""
        exit 1
    else
        echo "✅ All tests passed! Proceeding with push..."
    fi
else
    echo "⚠️  Test runner not found at: $WORK_DIR/run_all_tests.sh"
    echo "   Tests cannot be run automatically."
    echo "   Consider running tests manually before pushing."
    # Don't block the push if test runner is missing
    exit 0
fi

exit 0
EOF
    chmod +x "$WORKTREE_HOOKS_DIR/pre-push"
    echo "✓ Pre-push hook installed in worktree"
else
    echo "✗ Warning: run_all_tests.sh not found"
    echo "  Tests won't run automatically before push"
fi

# Install UI test dependencies if pyproject.toml has ui-tests extra
if grep -q "ui-tests" pyproject.toml 2>/dev/null; then
    echo ""
    echo "Installing UI test dependencies..."
    if command -v uv &> /dev/null; then
        uv sync --extra ui-tests
        echo "✓ UI test dependencies installed"
    else
        echo "✗ Warning: uv not found, skipping UI test setup"
    fi
fi

# Activate the workspace environment directly
echo ""
echo "Activating workspace environment..."

# Load environment variables from .env
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
    echo "✓ Loaded environment variables from .env"
fi

echo "✓ Workspace environment activated"

# Download/refresh AdCP schemas from official registry
echo ""
echo "📥 Downloading AdCP schemas from official registry..."
echo "   Source: https://adcontextprotocol.org/schemas/v1/"
if command -v uv &> /dev/null && [ -f "scripts/refresh_adcp_schemas.py" ]; then
    # Run schema refresh to ensure we have latest schemas
    if uv run python scripts/refresh_adcp_schemas.py 2>&1 | grep -E "✅|📥|📦"; then
        echo "✓ AdCP schemas downloaded/refreshed successfully"
    else
        echo "⚠️  Warning: Schema download may have had issues"
        echo "   Checking if cached schemas exist..."
        if [ -f "schemas/v1/index.json" ]; then
            echo "✓ Cached schemas found, continuing with setup"
        else
            echo "✗ No schemas available! This may cause validation issues."
        fi
    fi
else
    if ! command -v uv &> /dev/null; then
        echo "✗ Warning: uv not found, skipping schema download"
    elif [ ! -f "scripts/refresh_adcp_schemas.py" ]; then
        echo "✗ Warning: schema refresh script not found, skipping"
    fi
fi

# Generate AdCP Pydantic schemas from downloaded JSON schemas
echo ""
echo "🔧 Generating Pydantic schemas from AdCP spec..."
if command -v uv &> /dev/null && [ -f "scripts/generate_schemas.py" ]; then
    if uv run python scripts/generate_schemas.py 2>&1 | grep -E "✅|📂|🔧"; then
        echo "✓ Pydantic schemas generated successfully"
    else
        echo "⚠️  Warning: Pydantic schema generation may have had issues"
        echo "   Continuing with setup..."
    fi
else
    if ! command -v uv &> /dev/null; then
        echo "✗ Warning: uv not found, skipping Pydantic schema generation"
    elif [ ! -f "scripts/generate_schemas.py" ]; then
        echo "✗ Warning: Pydantic schema generation script not found, skipping"
    fi
fi

# Check AdCP schema sync
echo ""
echo "🔍 Verifying AdCP schema sync..."
if command -v uv &> /dev/null && [ -f "scripts/check_schema_sync.py" ]; then
    # Run schema sync check (but don't fail setup if schemas are out of sync)
    if uv run python scripts/check_schema_sync.py 2>&1 | tee /tmp/schema_check_output.txt; then
        echo "✓ AdCP schemas are in sync"
    else
        echo ""
        echo "⚠️  WARNING: AdCP schemas are out of sync!"
        echo "   This may cause integration issues with creative agent."
        echo ""
        echo "   To update schemas, run:"
        echo "   uv run python scripts/check_schema_sync.py --update"
        echo "   git add schemas/"
        echo "   git commit -m 'Update AdCP schemas to latest from registry'"
        echo ""
        echo "   Continuing with setup..."
    fi
else
    if ! command -v uv &> /dev/null; then
        echo "✗ Warning: uv not found, skipping schema sync check"
    elif [ ! -f "scripts/check_schema_sync.py" ]; then
        echo "✗ Warning: schema sync script not found, skipping check"
    fi
fi

echo ""
echo "Setup complete! Next steps:"
echo ""
echo "For development (with hot-reload):"
echo "   docker compose -f docker-compose.dev.yml up"
echo ""
echo "For production-style testing:"
echo "   docker compose up -d"
echo ""
echo "Services will be available at:"
echo "  http://localhost:\$CONDUCTOR_PORT/       -> Admin UI"
echo "  http://localhost:\$CONDUCTOR_PORT/admin  -> Admin UI"
echo "  http://localhost:\$CONDUCTOR_PORT/mcp    -> MCP Server"
echo "  http://localhost:\$CONDUCTOR_PORT/a2a    -> A2A Server"
echo ""
echo "Your CONDUCTOR_PORT is: ${CONDUCTOR_PORT:-8000}"
echo ""
echo "✓ Environment variables from .env are now active in this shell"
echo ""
echo "You can now run commands directly:"
echo "  a2a send http://localhost:8091 'Hello'"
echo "  pytest"
echo "  pre-commit run --all-files"
if [ -d "ui_tests" ]; then
    echo ""
    echo "UI Testing:"
    echo "  Run tests: cd ui_tests && uv run python -m pytest"
    echo "  Claude subagent: cd ui_tests/claude_subagent && ./run_subagent.sh"
fi
