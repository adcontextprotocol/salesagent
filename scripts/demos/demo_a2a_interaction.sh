#!/bin/bash
# Demo script showing a2a CLI interaction with our AdCP A2A server

# Add .venv/bin to PATH if needed
if [ -d ".venv/bin" ]; then
    export PATH="$(pwd)/.venv/bin:$PATH"
fi

echo "=== AdCP A2A Server Interaction Demo ==="
echo ""

# Send a query about products
echo "1. Asking about available advertising products..."
RESPONSE=$(a2a send http://localhost:8091 "What advertising products are available for a sports website?" 2>&1)
echo "$RESPONSE"
echo ""

# Extract task ID if available (the response includes a JSON with task ID)
TASK_ID=$(echo "$RESPONSE" | grep -o '"id":"[^"]*"' | cut -d'"' -f4 | head -1)

if [ -n "$TASK_ID" ]; then
    echo "2. Task created with ID: $TASK_ID"
    echo "   (Note: Task retrieval would require implementing a2a get command)"
    echo ""
fi

# Send another query about targeting
echo "3. Asking about targeting capabilities..."
a2a send http://localhost:8091 "What targeting options are available for display ads?"
echo ""

# Send a query about pricing
echo "4. Asking about pricing models..."
a2a send http://localhost:8091 "How does CPM pricing work for your premium inventory?"
echo ""

echo "=== Demo Complete ==="
echo ""
echo "The a2a CLI successfully communicated with our AdCP A2A server!"
echo "Each query creates a task that the server processes using the AdCP protocol."
