# MCP Client Usage Guide

## Overview

The AdCP Sales Agent server implements the MCP (Model Context Protocol) interface using FastMCP. This guide explains how to correctly call AdCP tools through the MCP protocol.

## Key Findings

### 1. Parameter Format

When calling tools through the MCP client, parameters must be wrapped in a `req` object:

```python
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

# CORRECT - Parameters wrapped in 'req'
result = await client.call_tool('get_products', {
    'req': {
        'brief': 'Display advertising products'
    }
})

# INCORRECT - Direct parameters
result = await client.call_tool('get_products', {
    'brief': 'Display advertising products'
})
```

### 2. Authentication

Authentication requires two headers:
- `x-adcp-auth`: The access token from the principals table
- `x-adcp-tenant`: The tenant ID (optional, defaults to 'default')

```python
headers = {
    "x-adcp-auth": "token_6119345e4a080d7223ee631062ca0e9e",
    "x-adcp-tenant": "default"
}
transport = StreamableHttpTransport(server_url, headers=headers)
```

### 3. Database Compatibility

The server handles both PostgreSQL (JSONB) and SQLite (JSON strings) databases. JSON fields are automatically parsed when needed.

### 4. Required Fields

Some tools have required fields per the AdCP specification:
- `get_products` requires a `brief` field (string)
- `create_media_buy` requires `product_ids`, `total_budget`, `flight_start_date`, and `flight_end_date`

## Complete Example

```python
import asyncio
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

async def example_mcp_usage():
    # Setup
    server_url = "http://localhost:8080/mcp/"
    headers = {
        "x-adcp-auth": "your_access_token",
        "x-adcp-tenant": "your_tenant_id"
    }
    
    transport = StreamableHttpTransport(server_url, headers=headers)
    
    async with Client(transport) as client:
        # 1. Get Products
        products_result = await client.call_tool('get_products', {
            'req': {
                'brief': 'Show all advertising products'
            }
        })
        
        if hasattr(products_result, 'products'):
            print(f"Found {len(products_result.products)} products")
            product_id = products_result.products[0].product_id
        
        # 2. Create Media Buy
        media_buy_result = await client.call_tool('create_media_buy', {
            'req': {
                'product_ids': [product_id],
                'total_budget': 5000.0,
                'flight_start_date': '2025-02-01',
                'flight_end_date': '2025-02-28'
            }
        })
        
        if hasattr(media_buy_result, 'media_buy_id'):
            print(f"Created media buy: {media_buy_result.media_buy_id}")

# Run the example
asyncio.run(example_mcp_usage())
```

## Troubleshooting

### Issue: "'req' is a required property"
**Solution**: Wrap your parameters in a `req` object as shown above.

### Issue: "the JSON object must be str, bytes or bytearray, not dict"
**Solution**: This was a server-side bug with PostgreSQL JSONB handling, now fixed. Ensure you're running the latest server version.

### Issue: "Missing or invalid x-adcp-auth header"
**Solution**: Ensure you're providing valid authentication headers with a token from the principals table.

### Issue: "Session expired" when using Admin UI
**Solution**: The Admin UI uses session-based authentication. Login through the web interface first.

## Testing with Admin UI

The Admin UI includes an MCP testing interface at `/mcp-test` (super admin only). This provides:
- Step-by-step workflow testing
- Debug modal showing raw request/response data
- Automatic parameter formatting
- Session-based authentication

Access it at: http://localhost:8001/mcp-test (requires super admin login)

## Notes on Implementation

The server uses FastMCP's `@mcp.tool` decorator which:
1. Transforms regular functions into MCP-compatible tools
2. Expects the first parameter to be a Pydantic model (e.g., `GetProductsRequest`)
3. Automatically handles parameter validation
4. Returns Pydantic response models

This is why parameters must be wrapped in `req` - it matches the function signature:
```python
@mcp.tool
async def get_products(req: GetProductsRequest, context: Context) -> GetProductsResponse:
```

The `context` parameter is automatically injected by FastMCP and contains HTTP request information for authentication.