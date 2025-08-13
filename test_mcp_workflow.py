#!/usr/bin/env python3
"""
Test the actual MCP tools available vs AdCP spec.
"""

import json
import subprocess
import sys

def call_mcp_tool(tool_name, params):
    """Helper to call an MCP tool."""
    result = subprocess.run([
        'curl', '-s', '-X', 'POST', 'http://localhost:8001/api/mcp-test/call',
        '-H', 'Content-Type: application/json',
        '-H', 'X-Debug-Mode: test',
        '-d', json.dumps({
            "tool": tool_name,
            "params": params,
            "access_token": "token_6119345e4a080d7223ee631062ca0e9e",
            "server_url": "http://localhost:8005/mcp/"
        })
    ], capture_output=True, text=True)
    
    try:
        return json.loads(result.stdout)
    except:
        return {"success": False, "error": f"Failed to parse: {result.stdout[:200]}"}

def test_mcp_workflow():
    """Test the complete MCP workflow with correct tool names."""
    
    print("=" * 70)
    print("MCP WORKFLOW TEST - Testing Actual vs Spec Tool Names")
    print("=" * 70)
    
    # Test 1: get_products (AdCP spec compliant)
    print("\n1. Testing get_products (AdCP spec: ✓)...")
    result = call_mcp_tool("get_products", {
        "brief": "Display advertising for general campaign",
        "promoted_offering": "Test advertiser - various products"
    })
    
    if result.get('success'):
        products = result.get('result', {}).get('products', [])
        print(f"  ✅ SUCCESS - Found {len(products)} products")
        if products:
            print(f"     First product: {products[0].get('product_id')}")
    else:
        print(f"  ❌ FAILED: {result.get('error')}")
        return False
    
    # Test 2: create_media_buy (AdCP spec compliant)
    print("\n2. Testing create_media_buy (AdCP spec: ✓)...")
    result = call_mcp_tool("create_media_buy", {
        "product_ids": ["test_display_300x250"],
        "flight_start_date": "2025-09-01",
        "flight_end_date": "2025-09-30",
        "total_budget": 5000,
        "targeting_overlay": {"geo_country_any_of": ["US"]}
    })
    
    media_buy_id = None
    if result.get('success'):
        media_buy_id = result.get('result', {}).get('media_buy_id')
        print(f"  ✅ SUCCESS - Created media buy: {media_buy_id}")
    else:
        print(f"  ❌ FAILED: {result.get('error')}")
    
    # Test 3: list_media_buys / get_media_buys (NOT in AdCP spec!)
    print("\n3. Testing list_media_buys (AdCP spec: ✗ - NOT DEFINED)...")
    result = call_mcp_tool("list_media_buys", {})
    if not result.get('success'):
        print(f"  ✅ CORRECT - Tool doesn't exist (not in spec)")
    else:
        print(f"  ❌ UNEXPECTED - Tool exists but not in AdCP spec!")
    
    # Test 4: check_media_buy_status (Use context_id from create_media_buy)
    # NOTE: get_principal_summary has been removed - use check_media_buy_status instead
    print("\n4. Skipping deprecated get_principal_summary test...")
    print("   Use check_media_buy_status with context_id from create_media_buy")
    
    # Test 5: add_creative_assets (AdCP spec name)
    print("\n5. Testing add_creative_assets (AdCP spec: ✓)...")
    result = call_mcp_tool("add_creative_assets", {
        "media_buy_id": media_buy_id or "test_buy",
        "assets": [{
            "id": "creative_test",
            "name": "Test Creative",
            "format": "display_300x250",
            "media_url": "https://example.com/banner.jpg",
            "click_url": "https://example.com/click"
        }]
    })
    
    if not result.get('success'):
        error = result.get('error', '')
        if 'Unknown tool' in error:
            print(f"  ❌ Tool not implemented (spec says it should exist)")
        else:
            print(f"  ❌ FAILED: {error}")
    else:
        print(f"  ✅ SUCCESS")
    
    # Test 6: add_creative_assets (Our implementation)
    print("\n6. Testing add_creative_assets (Our implementation, not in spec)...")
    result = call_mcp_tool("add_creative_assets", {
        "media_buy_id": media_buy_id or "test_buy",
        "creatives": [{
            "creative_id": "creative_test_001",
            "principal_id": "test_principal",
            "format_id": "display_300x250",
            "name": "Test Banner",
            "content_uri": "https://example.com/banner.jpg",
            "created_at": "2025-08-13T00:00:00Z"
        }]
    })
    
    if result.get('success'):
        print(f"  ✅ SUCCESS - This is what we use instead of add_creative_assets")
    else:
        print(f"  ❌ FAILED: {result.get('error')}")
    
    # Test 7: get_media_buy_delivery (AdCP spec compliant)
    print("\n7. Testing get_media_buy_delivery (AdCP spec: ✓)...")
    result = call_mcp_tool("get_media_buy_delivery", {
        "media_buy_id": media_buy_id or "test_buy",
        "today": "2025-08-12"
    })
    
    if result.get('success'):
        print(f"  ✅ SUCCESS")
    else:
        error = result.get('error', '')
        if 'Unknown tool' in error:
            print(f"  ❌ Tool not found - might be named differently")
        else:
            print(f"  ⚠️  Error: {error[:100]}")
    
    # Summary
    print("\n" + "=" * 70)
    print("TOOL NAME MAPPING:")
    print("-" * 70)
    print("AdCP Spec Name         → Our Implementation")
    print("-" * 70)
    print("get_products           → get_products ✓")
    print("create_media_buy       → create_media_buy ✓")
    print("list_media_buys        → NOT IN SPEC (removed - use check_media_buy_status)")
    print("add_creative_assets    → add_creative_assets (different!)")
    print("get_media_buy_delivery → get_media_buy_delivery ✓")
    print("update_media_buy       → update_media_buy ✓")
    print("=" * 70)
    
    return True

if __name__ == "__main__":
    test_mcp_workflow()
    sys.exit(0)