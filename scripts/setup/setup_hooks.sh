#!/bin/bash
# Script to set up Git hooks for the project

echo "Setting up Git hooks..."

# Get the git directory
GIT_DIR=$(git rev-parse --git-dir)

# Create hooks directory if it doesn't exist
mkdir -p "$GIT_DIR/hooks"

# Create pre-push hook (only checks migrations, no tests)
cat > "$GIT_DIR/hooks/pre-push" << 'EOF'
#!/bin/bash
# Pre-push hook to check migrations before pushing to remote
# Tests run in CI - this hook keeps pushes fast

# Get the directory of the git repository
GIT_DIR=$(git rev-parse --show-toplevel)
cd "$GIT_DIR"

# Check for multiple Alembic migration heads (fast check)
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

echo "✅ Pre-push checks passed!"
echo ""
echo "💡 To run tests locally before pushing:"
echo "   ./run_all_tests.sh quick   # Fast (~1 min, no database)"
echo "   ./run_all_tests.sh ci      # Full (~3-5 min, with PostgreSQL)"

exit 0
EOF

# Make hook executable
chmod +x "$GIT_DIR/hooks/pre-push"

echo "✅ Git hooks installed successfully!"
echo ""
echo "Pre-push hook: Migration head checks only (fast)"
echo "Pre-commit hook: Code quality checks (formatting, linting)"
echo "CI: Full test suite runs automatically on GitHub"
