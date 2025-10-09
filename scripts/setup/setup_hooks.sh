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

echo "🔍 Running CI-mode tests before push (with PostgreSQL)..."
echo "   This matches exactly what GitHub Actions will run."
echo ""

# Check if test runner exists
if [ -f "./run_all_tests.sh" ]; then
    # Run CI mode tests (with PostgreSQL container, like GitHub Actions)
    ./run_all_tests.sh ci
    TEST_RESULT=$?

    if [ $TEST_RESULT -ne 0 ]; then
        echo ""
        echo "❌ Tests failed! Push aborted."
        echo ""
        echo "The CI-mode tests (which match GitHub Actions) failed."
        echo "This catches database-specific issues before they hit CI."
        echo ""
        echo "To push anyway (not recommended):"
        echo "  git push --no-verify"
        echo ""
        exit 1
    else
        echo ""
        echo "✅ All CI-mode tests passed! Proceeding with push..."
        echo "   Your code is ready for GitHub Actions."
    fi
else
    echo "⚠️  Test runner not found. Skipping tests."
    echo "   Consider running: ./run_all_tests.sh ci"
fi

exit 0
EOF

# Make hook executable
chmod +x "$GIT_DIR/hooks/pre-push"

echo "✅ Git hooks installed successfully!"
echo ""
echo "The pre-push hook will now run tests before each push."
echo "To skip tests temporarily, use: git push --no-verify"
