#!/bin/bash
# Script to set up Git hooks for the project

echo "Setting up Git hooks..."

# Get the git directory
GIT_DIR=$(git rev-parse --git-dir)

# Create hooks directory if it doesn't exist
mkdir -p "$GIT_DIR/hooks"

# Create pre-push hook
cat > "$GIT_DIR/hooks/pre-push" << 'EOF'
#!/bin/bash
# Pre-push hook to check migrations and run tests before pushing to remote

# Get the directory of the git repository
GIT_DIR=$(git rev-parse --show-toplevel)
cd "$GIT_DIR"

# Check for multiple Alembic migration heads first (fast check)
echo "🔍 Checking for multiple migration heads..."
if command -v uv &> /dev/null; then
    uv run python scripts/ops/check_migration_heads.py --quiet
    MIGRATION_CHECK=$?

    if [ $MIGRATION_CHECK -ne 0 ]; then
        echo ""
        echo "❌ Multiple migration heads detected!"
        echo ""
        echo "This will cause CI failures. To fix:"
        echo "  1. Auto-fix: uv run python scripts/ops/check_migration_heads.py --fix"
        echo "  2. Interactive: ./scripts/ops/auto_merge_migrations.sh"
        echo ""
        echo "To push anyway (not recommended):"
        echo "  git push --no-verify"
        echo ""
        exit 1
    fi
    echo "✅ Migration heads OK"
    echo ""
fi

echo "🔍 Running quick tests before push (no PostgreSQL required)..."
echo "   Unit tests + integration tests (mocked database)"
echo ""

# Check if test runner exists
if [ -f "./run_all_tests.sh" ]; then
    # Run QUICK mode tests (unit + integration without database)
    # Fast validation that doesn't require PostgreSQL containers
    ./run_all_tests.sh quick
    TEST_RESULT=$?

    if [ $TEST_RESULT -ne 0 ]; then
        echo ""
        echo "❌ Quick tests failed! Push aborted."
        echo ""
        echo "To run full CI tests locally (with PostgreSQL):"
        echo "  ./run_all_tests.sh ci"
        echo ""
        echo "To push anyway (not recommended):"
        echo "  git push --no-verify"
        echo ""
        exit 1
    else
        echo ""
        echo "✅ Quick tests passed! Proceeding with push..."
        echo "   Full CI tests (with PostgreSQL) will run in GitHub Actions."
    fi
else
    echo "⚠️  Test runner not found. Skipping tests."
    echo "   Consider running: ./run_all_tests.sh quick"
fi

exit 0
EOF

# Make hook executable
chmod +x "$GIT_DIR/hooks/pre-push"

echo "✅ Git hooks installed successfully!"
echo ""
echo "The pre-push hook will run quick tests (no PostgreSQL) before each push."
echo "Full CI tests will run in GitHub Actions."
echo "To skip tests temporarily, use: git push --no-verify"
