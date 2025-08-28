# 🧪 AdCP E2E Testing - Complete Guide

This project now has comprehensive end-to-end testing for the AdCP protocol with full request/response visibility.

## 🚀 Quick Start

```bash
# 1. Start the test environment
./start_test_services.sh

# 2. Run debug script to see the protocol in action
python run_debug_e2e.py

# 3. Run individual tests
uv run pytest tests/e2e/test_adcp_full_lifecycle.py::TestAdCPFullLifecycle::test_product_discovery -v -s
```

## 📁 Key Files

| File | Purpose |
|------|---------|
| `TEST_DEBUGGING_GUIDE.md` | **Complete debugging guide** - Start here! |
| `start_test_services.sh` | Starts Docker services with health checks |
| `run_debug_e2e.py` | Shows detailed request/response data |
| `tests/e2e/test_adcp_full_lifecycle.py` | **Enhanced E2E test suite** |

## 🎯 What the E2E Tests Cover

### Core AdCP Protocol Flow
1. **Product Discovery** - `get_products` with natural language queries
2. **Media Buy Creation** - `create_media_buy` with targeting & validation
3. **Creative Management** - `add_creative_assets` with multiple formats
4. **Delivery Reporting** - `get_media_buy_delivery` with metrics validation

### Protocol Support
- ✅ **MCP Protocol** - All core tools with comprehensive validation
- ✅ **A2A Protocol** - Natural language queries with response validation
- ✅ **Testing Hooks** - X-Dry-Run, X-Mock-Time, X-Test-Session-ID

### Validation Features
- ✅ **Field Validation** - All required fields per AdCP spec
- ✅ **Data Type Checking** - Strings, numbers, arrays, objects
- ✅ **Business Logic** - Budget validation, date ranges, etc.
- ✅ **Error Handling** - Invalid inputs, missing data, etc.

## 🔍 What You'll See

### Request/Response Flow
```
🔵 MCP REQUEST: get_products
   URL: http://localhost:8155/mcp/
   Headers: {"x-adcp-auth": "...", "X-Dry-Run": "true"}
   Params: {"brief": "Looking for display advertising"}

🟢 MCP RESPONSE: get_products
   Response: {
     "products": [
       {
         "product_id": "prod_1",
         "name": "Premium Display Package",
         "formats": [{"format_id": "display_300x250", ...}]
       }
     ]
   }
```

### Test Validation Output
```
=== Testing Product Discovery ===
  Validating product 1: Premium Display Package
    • Product ID: prod_1 ✓
    • Name: Premium Display Package ✓
    • Formats: 3 formats found ✓
    • Pricing: CPM model, $2.50-$8.00 range ✓
✓ MCP: Found 6 products with complete validation
✓ A2A: Product information validated successfully
```

## 📊 Test Results

The enhanced tests provide:
- **100% coverage** of core AdCP protocol methods
- **Field-level validation** against the AdCP specification
- **Both protocol testing** (MCP and A2A)
- **Real-time debugging** with request/response visibility
- **Comprehensive assertions** with clear error messages

## 🎬 GitHub Issues for Future Work

Created 8 strategic issues for expanding E2E testing:
- **#89**: Creative Format Management
- **#90**: Advanced Targeting Capabilities
- **#91**: Multi-Tenant Isolation
- **#92**: Performance Optimization Features
- **#93**: Error Handling & Recovery
- **#94**: Manual Approval Workflows
- **#95**: Bulk Operations
- **#96**: Performance & Scale Testing

## 🛠️ Development Workflow

```bash
# Start development
./start_test_services.sh

# Debug specific functionality
python run_debug_e2e.py

# Run focused tests
uv run pytest tests/e2e/test_adcp_full_lifecycle.py::TestAdCPFullLifecycle::test_creative_workflow -v -s

# View server logs
docker-compose logs -f

# Stop when done
docker-compose down
```

## 📚 Documentation

- **`TEST_DEBUGGING_GUIDE.md`** - Complete guide with examples
- **Test method docstrings** - Detailed explanation of each test
- **Inline comments** - Clear validation logic
- **Error messages** - Specific failure reasons

## ✨ Key Features

### Enhanced Test Client
- **Request logging** - See exact HTTP requests
- **Response parsing** - Structured JSON output
- **Error handling** - Clear failure messages
- **Testing hooks** - X-Dry-Run, X-Mock-Time support

### Comprehensive Validation
- **Required fields** - Per AdCP specification
- **Data types** - Strings, numbers, arrays validation
- **Business rules** - Budgets, dates, targeting rules
- **Cross-protocol** - MCP and A2A consistency

### Production Ready
- **Docker integration** - Isolated test environment
- **Health checks** - Ensure services are ready
- **Cleanup** - Proper resource management
- **CI/CD ready** - Automated test execution

---

**Ready to test the AdCP protocol?** Start with `./start_test_services.sh` and `python run_debug_e2e.py`! 🚀
