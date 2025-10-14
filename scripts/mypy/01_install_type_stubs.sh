#!/bin/bash
# Install missing type stubs for better mypy checking

set -e

echo "Installing type stubs..."

# Install type stubs for external libraries
uv add --dev types-psycopg2 types-requests types-pytz types-waitress

# Configure mypy to ignore libraries without stubs
echo ""
echo "Configuring mypy.ini for libraries without type stubs..."

# Check if googleads section already exists
if ! grep -q "\[mypy-googleads\.\*\]" mypy.ini; then
    cat >> mypy.ini << 'EOF'

# Libraries without type stubs (ignore missing imports)
[mypy-googleads.*]
ignore_missing_imports = True

[mypy-authlib.*]
ignore_missing_imports = True

[mypy-flask_socketio.*]
ignore_missing_imports = True
EOF
    echo "✓ Updated mypy.ini"
else
    echo "✓ mypy.ini already configured"
fi

echo ""
echo "✓ Type stubs installed successfully"
echo ""
echo "Run 'uv run mypy src/' to see the improvement"
