#!/bin/bash
# Install git hooks for migration head checking
#
# This script installs pre-push hooks that check for multiple Alembic migration
# heads and optionally auto-merge them.

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$SCRIPT_DIR/../.."
GIT_DIR="$PROJECT_ROOT/../../.git"

if [ ! -d "$GIT_DIR" ]; then
    echo "❌ Git directory not found at $GIT_DIR"
    exit 1
fi

HOOKS_DIR="$GIT_DIR/hooks"

echo "🔧 Installing git hooks..."

# Create or update pre-push hook
cat > "$HOOKS_DIR/pre-push.new" << 'HOOK_EOF'
#!/bin/bash
# Pre-push hook to run tests and check migrations before pushing to remote

echo "Running pre-push checks..."

# Get the directory of the git repository
GIT_DIR=$(git rev-parse --show-toplevel)

# Find the conductor workspace directory
WORKSPACE_DIR="$GIT_DIR/.conductor/salvador"
if [ ! -d "$WORKSPACE_DIR" ]; then
    echo "⚠️  Conductor workspace not found, skipping migration checks"
    WORKSPACE_DIR="$GIT_DIR"
fi

cd "$WORKSPACE_DIR"

# Check for multiple migration heads BEFORE running tests
echo ""
echo "🔍 Checking Alembic migration heads..."
if ! uv run python scripts/ops/check_migration_heads.py --quiet; then
    echo ""
    echo "❌ Multiple Alembic migration heads detected!"
    echo ""
    echo "This happens when multiple branches add migrations and are merged."
    echo ""
    echo "Options:"
    echo "  1. Auto-merge (recommended):"
    echo "     ./scripts/ops/auto_merge_migrations.sh"
    echo ""
    echo "  2. Manual merge:"
    echo "     uv run alembic merge -m 'Merge migration heads' head"
    echo "     git add alembic/versions/*.py"
    echo "     git commit -m 'Merge Alembic migration heads'"
    echo ""
    echo "  3. Skip check (NOT recommended):"
    echo "     git push --no-verify"
    echo ""
    exit 1
fi

echo "✅ Migration heads OK"
echo ""

# Check if test runner exists
if [ -f "./run_all_tests.sh" ]; then
    # Run CI mode tests (with PostgreSQL)
    echo "Running tests in CI mode (with PostgreSQL)..."
    ./run_all_tests.sh ci
    TEST_RESULT=$?

    if [ $TEST_RESULT -ne 0 ]; then
        echo ""
        echo "❌ Tests failed! Push aborted."
        echo ""
        echo "To push anyway (not recommended):"
        echo "  git push --no-verify"
        echo ""
        exit 1
    else
        echo "✅ All tests passed! Proceeding with push..."
    fi
else
    echo "⚠️  Test runner not found. Skipping tests."
    echo "   Consider running: ./run_all_tests.sh"
fi

exit 0
HOOK_EOF

# Make it executable
chmod +x "$HOOKS_DIR/pre-push.new"

# Backup existing hook if present
if [ -f "$HOOKS_DIR/pre-push" ]; then
    cp "$HOOKS_DIR/pre-push" "$HOOKS_DIR/pre-push.backup.$(date +%Y%m%d_%H%M%S)"
    echo "📦 Backed up existing pre-push hook"
fi

# Install new hook
mv "$HOOKS_DIR/pre-push.new" "$HOOKS_DIR/pre-push"

echo "✅ Git hooks installed successfully"
echo ""
echo "Installed hooks:"
echo "  - pre-push: Check migration heads + run CI tests"
echo ""
echo "To bypass hooks (not recommended):"
echo "  git push --no-verify"
