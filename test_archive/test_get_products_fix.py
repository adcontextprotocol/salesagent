#!/usr/bin/env python3
"""
Test script to verify the get_products Pydantic validation fix.
"""

import asyncio
import sys
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport


async def test_get_products_fix():
    """Test that get_products now works without Pydantic validation errors."""
    
    print("Testing get_products fix...")
    
    headers = {'x-adcp-auth': 'token_6119345e4a080d7223ee631062ca0e9e'}
    transport = StreamableHttpTransport(
        url='http://localhost:8005/mcp/', 
        headers=headers
    )
    
    try:
        async with Client(transport=transport) as client:
            # Try to call the get_products tool
            result = await client.call_tool(
                "get_products", 
                {"req": {"brief": "video advertising for sports content"}}
            )
            
            print("✅ SUCCESS: get_products call completed!")
            print(f"Result type: {type(result)}")
            
            # Check if we got products back
            if hasattr(result, 'content') and len(result.content) > 0:
                content = result.content[0]
                if hasattr(content, 'text'):
                    import json
                    try:
                        response_data = json.loads(content.text)
                        products = response_data.get('products', [])
                        print(f"✅ Got {len(products)} products")
                        
                        if products:
                            # Check first product has required fields
                            first_product = products[0]
                            required_fields = ['product_id', 'name', 'description', 'formats', 'is_custom']
                            
                            for field in required_fields:
                                if field in first_product:
                                    print(f"✅ Field '{field}': {first_product[field]}")
                                else:
                                    print(f"❌ Missing field '{field}'")
                            
                            # Check format structure
                            if first_product.get('formats'):
                                first_format = first_product['formats'][0]
                                format_required = ['format_id', 'name', 'description', 'delivery_options']
                                
                                print("\nFormat validation:")
                                for field in format_required:
                                    if field in first_format:
                                        print(f"✅ Format field '{field}': {first_format[field]}")
                                    else:
                                        print(f"❌ Missing format field '{field}'")
                        
                    except json.JSONDecodeError as e:
                        print(f"❌ Failed to parse JSON response: {e}")
                        print(f"Raw response: {content.text[:200]}...")
                
            return True
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_get_products_fix())
    if success:
        print("\n🎉 All tests passed! The Pydantic validation fix is working.")
        sys.exit(0)
    else:
        print("\n💥 Tests failed. Please check the logs.")
        sys.exit(1)