#!/usr/bin/env python3
"""
Test to ensure implementation_config is NEVER exposed in get_products responses.
This is critical for security as implementation_config contains proprietary 
ad server configuration that buyers should not see.
"""

import asyncio
import json
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

async def test_implementation_config_not_exposed():
    """Test that implementation_config is never exposed in get_products response."""
    
    # Test configuration
    server_url = "http://localhost:8005/mcp/"
    access_token = "token_6119345e4a080d7223ee631062ca0e9e"
    
    # Set up MCP client
    headers = {"x-adcp-auth": access_token, "x-adcp-tenant": "test_publisher"}
    transport = StreamableHttpTransport(server_url, headers=headers)
    
    async with Client(transport) as client:
        # Call get_products
        print("Testing get_products to ensure implementation_config is not exposed...")
        
        arguments = {
            "req": {
                "brief": "Show all available advertising products"
            }
        }
        
        result = await client.call_tool("get_products", arguments)
        
        # Check if result has structured_content or needs parsing
        if hasattr(result, 'structured_content'):
            products_data = result.structured_content
        elif hasattr(result, 'data') and hasattr(result.data, 'products'):
            products_data = {"products": [p.model_dump() for p in result.data.products]}
        elif hasattr(result, 'content') and isinstance(result.content, list):
            # Parse from TextContent
            text_content = result.content[0].text if result.content else "{}"
            products_data = json.loads(text_content)
        else:
            products_data = {"products": []}
        
        # Check each product
        products = products_data.get('products', [])
        
        print(f"\nFound {len(products)} products")
        
        # Test results
        test_passed = True
        for product in products:
            print(f"\nChecking product: {product.get('product_id', 'unknown')}")
            
            # Check if implementation_config exists
            if 'implementation_config' in product:
                if product['implementation_config'] is not None:
                    print(f"  ❌ FAIL: implementation_config is exposed with value: {product['implementation_config']}")
                    test_passed = False
                else:
                    print(f"  ⚠️  WARNING: implementation_config field exists but is null")
            else:
                print(f"  ✅ PASS: implementation_config field not present")
            
            # Also check the raw JSON to be sure
            product_json = json.dumps(product)
            if 'implementation_config' in product_json and '"implementation_config": null' not in product_json:
                print(f"  ❌ FAIL: implementation_config found in JSON: {product_json[:200]}...")
                test_passed = False
        
        print("\n" + "="*60)
        if test_passed:
            print("✅ SUCCESS: implementation_config is NOT exposed to buyers")
            print("This is correct behavior - implementation_config is proprietary")
        else:
            print("❌ FAILURE: implementation_config IS EXPOSED - CRITICAL SECURITY ISSUE")
            print("implementation_config contains proprietary ad server details")
            print("and should NEVER be visible to buyers!")
        print("="*60)
        
        return test_passed

if __name__ == "__main__":
    # Run the test
    success = asyncio.run(test_implementation_config_not_exposed())
    exit(0 if success else 1)