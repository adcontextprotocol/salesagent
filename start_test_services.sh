#!/bin/bash

echo "🚀 Starting AdCP E2E Test Environment"
echo "===================================="

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker Desktop first."
    exit 1
fi

# Stop any existing services
echo "🧹 Cleaning up existing services..."
docker-compose down > /dev/null 2>&1

# Start services
echo "🔧 Starting Docker services..."
if docker-compose up -d; then
    echo "✅ Docker services started"
else
    echo "❌ Failed to start Docker services"
    exit 1
fi

echo ""
echo "⏳ Waiting for services to be ready..."

# Wait for MCP server (max 60 seconds)
MCP_READY=false
A2A_READY=false
TIMEOUT=60
ELAPSED=0

# Read ports from environment variables
MCP_PORT=${ADCP_SALES_PORT:-8166}
A2A_PORT=${A2A_PORT:-8091}

while [ $ELAPSED -lt $TIMEOUT ]; do
    # Check MCP health
    if [ "$MCP_READY" != "true" ]; then
        if curl -s http://localhost:$MCP_PORT/health > /dev/null 2>&1; then
            echo "✅ MCP server is ready (localhost:$MCP_PORT)"
            MCP_READY=true
        fi
    fi

    # Check A2A server
    if [ "$A2A_READY" != "true" ]; then
        if curl -s http://localhost:$A2A_PORT/ > /dev/null 2>&1; then
            echo "✅ A2A server is ready (localhost:$A2A_PORT)"
            A2A_READY=true
        fi
    fi

    # Both ready?
    if [ "$MCP_READY" = "true" ] && [ "$A2A_READY" = "true" ]; then
        break
    fi

    sleep 2
    ELAPSED=$((ELAPSED + 2))
    printf "."
done

echo ""

if [ "$MCP_READY" != "true" ] || [ "$A2A_READY" != "true" ]; then
    echo "❌ Services did not start in time"
    echo "   MCP Ready: $MCP_READY"
    echo "   A2A Ready: $A2A_READY"
    echo ""
    echo "📋 Service logs:"
    docker-compose logs --tail=20
    exit 1
fi

echo ""
echo "🎉 All services are ready!"
echo ""
echo "📊 Service URLs:"
echo "   MCP Server: http://localhost:$MCP_PORT"
echo "   A2A Server: http://localhost:$A2A_PORT"
echo "   Admin UI:   http://localhost:${ADMIN_UI_PORT:-8087}"
echo ""
echo "🧪 Ready to run tests! Try:"
echo "   python run_debug_e2e.py"
echo "   uv run pytest tests/e2e/test_adcp_full_lifecycle.py::TestAdCPFullLifecycle::test_product_discovery -v -s"
echo ""
echo "📜 To view logs:"
echo "   docker-compose logs -f"
echo ""
echo "🛑 To stop services:"
echo "   docker-compose down"
