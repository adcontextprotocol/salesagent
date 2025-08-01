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
# Pre-push hook to run tests before pushing to remote

echo "Running tests before push..."

# Get the directory of the git repository
GIT_DIR=$(git rev-parse --show-toplevel)
cd "$GIT_DIR"

# Check if test runner exists
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
    echo "⚠️  Test runner not found. Skipping tests."
    echo "   Consider running: ./run_all_tests.sh"
fi

exit 0
EOF

# Make hook executable
chmod +x "$GIT_DIR/hooks/pre-push"

echo "✅ Git hooks installed successfully!"
echo ""
echo "The pre-push hook will now run tests before each push."
echo "To skip tests temporarily, use: git push --no-verify"