#!/bin/bash
# Activation script for Conductor workspace

# Add .venv/bin to PATH if it exists
if [ -d ".venv/bin" ]; then
    export PATH="$(pwd)/.venv/bin:$PATH"
    echo "✓ Added .venv/bin to PATH"
fi

# Load environment variables from .env
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
    echo "✓ Loaded environment variables from .env"
fi

echo ""
echo "Conductor workspace activated!"
echo "You can now run commands directly:"
echo "  a2a send http://localhost:8091 'Hello'"
echo "  pytest"
echo "  pre-commit run --all-files"
