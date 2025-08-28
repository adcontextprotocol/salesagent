# 🧪 AdCP E2E Test Debugging Guide

This guide shows you exactly how to run the E2E tests and see all the request/response data flowing between your test client and the AdCP servers.

## 🚀 Quick Start

### 1. Start the Test Environment

```bash
# Start Docker services with health checks
./start_test_services.sh
```

This will:
- Start MCP server on port 8155
- Start A2A server on port 8091
- Start Admin UI on port 8076
- Wait for all services to be healthy
- Show you the service URLs

### 2. Run Debug Script (Recommended First)

```bash
# Run the debug script to see detailed request/response flow
python run_debug_e2e.py
```

This shows you EXACTLY what data is sent and received:

```
🔵 MCP REQUEST: get_products
   URL: http://localhost:8155/mcp/
   Headers: {
     "x-adcp-auth": "1sNG-OxWfEsELsey-6H6IGg1HCxrpbtneGfW4GkSb10",
     "X-Test-Session-ID": "abc123...",
     "X-Dry-Run": "true"
   }
   Params: {
     "brief": "Looking for display advertising",
     "promoted_offering": "test campaign"
   }

🟢 MCP RESPONSE: get_products
   Response: {
     "products": [
       {
         "product_id": "prod_1",
         "name": "Premium Display Package",
         "formats": [
           {
             "format_id": "display_300x250",
             "name": "Medium Rectangle"
           }
         ],
         "pricing": {...}
       }
     ]
   }
```

## 🧪 Different Ways to Run Tests

### Option 1: Run Individual Test Methods

```bash
# Run just the product discovery test with verbose output
uv run pytest tests/e2e/test_adcp_full_lifecycle.py::TestAdCPFullLifecycle::test_product_discovery -v -s

# Run the comprehensive A2A test
uv run pytest tests/e2e/test_adcp_full_lifecycle.py::TestAdCPFullLifecycle::test_a2a_protocol_comprehensive -v -s

# Run the delivery testing
uv run pytest tests/e2e/test_adcp_full_lifecycle.py::TestAdCPFullLifecycle::test_delivery_metrics_comprehensive -v -s
```

### Option 2: Run All E2E Tests

```bash
# Run the complete test suite
uv run pytest tests/e2e/test_adcp_full_lifecycle.py -v -s

# Run with even more detail
uv run pytest tests/e2e/test_adcp_full_lifecycle.py -v -s --tb=long
```

### Option 3: Run Tests with HTTP Request Logging

```bash
# Enable HTTP client debugging
export HTTPX_LOG_LEVEL=DEBUG
uv run pytest tests/e2e/test_adcp_full_lifecycle.py::TestAdCPFullLifecycle::test_product_discovery -v -s
```

## 📊 Understanding the Test Output

### MCP Protocol Flow

```
=== Testing Product Discovery ===
  Validating product 1: Premium Display Package
    • Product ID: prod_1 ✓
    • Name: Premium Display Package ✓
    • Formats: 3 formats found ✓
    • Format validation: display_300x250 ✓
✓ MCP: Found 6 products with complete validation

=== Testing A2A Protocol ===
  Testing A2A Product Discovery
    ✓ 'What advertising products do you...' completed successfully
    ✓ 'Show me display advertising...' completed successfully
✓ A2A: Product information validated successfully
```

### Request/Response Examples

**MCP Request:**
```json
{
  "method": "call_tool",
  "params": {
    "name": "get_products",
    "arguments": {
      "req": {
        "brief": "Looking for display advertising",
        "promoted_offering": "standard display ads"
      }
    }
  }
}
```

**MCP Response:**
```json
{
  "result": {
    "products": [
      {
        "product_id": "prod_sports_display",
        "name": "Sports Premium Display",
        "description": "High-impact display advertising for sports content",
        "formats": [
          {
            "format_id": "display_300x250",
            "name": "Medium Rectangle",
            "dimensions": {"width": 300, "height": 250}
          }
        ],
        "pricing": {
          "model": "cpm",
          "price_range": {"min": 2.50, "max": 8.00}
        }
      }
    ]
  }
}
```

**A2A Request:**
```json
{
  "message": "What display advertising products do you offer?",
  "thread_id": "test-session-123"
}
```

**A2A Response:**
```json
{
  "status": {"state": "completed"},
  "artifacts": [...],
  "message": "We offer several display advertising products including..."
}
```

## 🔍 Advanced Debugging

### 1. View Live Server Logs

```bash
# Watch all service logs
docker-compose logs -f

# Watch just the MCP server
docker-compose logs -f adcp-server

# Watch just the A2A server
docker-compose logs -f adcp-server | grep -i a2a
```

### 2. Test Specific Endpoints Manually

```bash
# Test MCP health
curl http://localhost:8155/health

# Test A2A server
curl http://localhost:8091/

# Test admin UI
curl http://localhost:8076/
```

### 3. Database Inspection

```bash
# Connect to the test database
docker exec -it a2a-e2e-postgres-1 psql -U adcp_user -d adcp

# View products
SELECT product_id, name FROM products LIMIT 5;

# View principals (auth tokens)
SELECT principal_id, name, access_token FROM principals LIMIT 5;
```

### 4. Custom Test Script

Create your own test script:

```python
import asyncio
from run_debug_e2e import DebugTestClient

async def my_custom_test():
    async with DebugTestClient("http://localhost:8155", "http://localhost:8091", "your-token") as client:

        # Your custom test here
        result = await client.call_mcp_tool("get_products", {"brief": "my query"})
        print("Custom result:", result)

asyncio.run(my_custom_test())
```

## 🐛 Troubleshooting

### Services Won't Start

```bash
# Check Docker is running
docker info

# Check port conflicts
lsof -i :8155
lsof -i :8091

# Clean restart
docker-compose down
docker system prune -f
./start_test_services.sh
```

### Authentication Failures

The tests use this token: `1sNG-OxWfEsELsey-6H6IGg1HCxrpbtneGfW4GkSb10`

If you get auth errors:
1. Check if the principal exists in the database
2. Create a new test principal via the admin UI
3. Update the token in `run_debug_e2e.py`

### Network Errors

```bash
# Check service health
curl -v http://localhost:8155/health
curl -v http://localhost:8091/

# Check Docker network
docker network ls
docker network inspect a2a-e2e_default
```

## 📈 Test Coverage

The enhanced E2E tests now cover:

✅ **Product Discovery** - MCP + A2A protocols
✅ **Media Buy Creation** - Complex targeting, validation
✅ **Creative Workflow** - Multiple formats, status tracking
✅ **Delivery Metrics** - Comprehensive reporting validation
✅ **A2A Protocol** - Natural language queries
✅ **Spec Compliance** - AdCP standard validation

Each test shows you the exact HTTP requests, headers, payloads, and responses.

## 🎯 Next Steps

1. Run `./start_test_services.sh` to get started
2. Run `python run_debug_e2e.py` to see the protocol in action
3. Try individual test methods to focus on specific areas
4. Customize the debug script for your specific testing needs

Happy testing! 🚀
