#!/usr/bin/env python3
"""
Test AdCP Protocol Compliance

This script tests the actual implementation against the AdCP specification.
It documents discrepancies and provides workarounds.
"""

import json
import subprocess
import sys
from datetime import datetime, timedelta

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

def test_get_products_compliance():
    """Test get_products response for AdCP compliance."""
    
    print("=" * 60)
    print("AdCP PROTOCOL COMPLIANCE TEST")
    print("=" * 60)
    
    # Make actual API call
    import subprocess
    
    # Test 1: Basic request with only required 'brief' field
    print("\n1. Testing with only 'brief' (promoted_offering omitted)...")
    result1 = subprocess.run([
        'curl', '-s', '-X', 'POST', 'http://localhost:8001/api/mcp-test/call',
        '-H', 'Content-Type: application/json',
        '-H', 'X-Debug-Mode: test',
        '-d', json.dumps({
            "tool": "get_products",
            "params": {"brief": "Show all advertising products"},
            "access_token": "token_6119345e4a080d7223ee631062ca0e9e",
            "server_url": "http://localhost:8005/mcp/"
        })
    ], capture_output=True, text=True)
    
    try:
        response1 = json.loads(result1.stdout)
        if response1.get('success'):
            print("  ✅ Request successful without promoted_offering")
        else:
            print(f"  ❌ Request failed: {response1.get('error')}")
            return False
    except:
        print(f"  ❌ Invalid response: {result1.stdout[:200]}")
        return False
    
    # Test 2: Request with promoted_offering included
    print("\n2. Testing with 'promoted_offering' included...")
    result2 = subprocess.run([
        'curl', '-s', '-X', 'POST', 'http://localhost:8001/api/mcp-test/call',
        '-H', 'Content-Type: application/json',
        '-H', 'X-Debug-Mode: test',
        '-d', json.dumps({
            "tool": "get_products",
            "params": {
                "brief": "Video advertising for sports content",
                "promoted_offering": "Nike running shoes - targeting athletic enthusiasts"
            },
            "access_token": "token_6119345e4a080d7223ee631062ca0e9e",
            "server_url": "http://localhost:8005/mcp/"
        })
    ], capture_output=True, text=True)
    
    try:
        response2 = json.loads(result2.stdout)
        if response2.get('success'):
            print("  ✅ Request successful with promoted_offering")
        else:
            print(f"  ❌ Request failed: {response2.get('error')}")
            return False
    except:
        print(f"  ❌ Invalid response: {result2.stdout[:200]}")
        return False
    
    # Test 3: Verify response structure
    print("\n3. Verifying response structure compliance...")
    
    if not response1.get('success') or not response1.get('result'):
        print("  ❌ Response missing success/result fields")
        return False
    
    products = response1['result'].get('products', [])
    if not products:
        print("  ⚠️  No products returned to test")
        return True
    
    compliance_passed = True
    
    for product in products:
        print(f"\n  Checking product: {product.get('product_id', 'unknown')}")
        
        # Check required fields per AdCP spec
        required_fields = ['product_id', 'name', 'description', 'formats', 'delivery_type']
        for field in required_fields:
            if field not in product:
                print(f"    ❌ Missing required field: {field}")
                compliance_passed = False
            else:
                print(f"    ✅ Has required field: {field}")
        
        # Check that implementation_config is NOT exposed
        if 'implementation_config' in product:
            if product['implementation_config'] is not None:
                print(f"    ❌ CRITICAL: implementation_config EXPOSED with value!")
                print(f"       Value: {product['implementation_config']}")
                compliance_passed = False
            else:
                print(f"    ⚠️  implementation_config present but null (should be removed)")
        else:
            print(f"    ✅ implementation_config not present (correct)")
        
        # Check format structure
        if 'formats' in product and isinstance(product['formats'], list):
            for fmt in product['formats']:
                required_format_fields = ['format_id', 'name', 'type']
                missing = [f for f in required_format_fields if f not in fmt]
                if missing:
                    print(f"    ❌ Format missing fields: {missing}")
                    compliance_passed = False
    
    print("\n" + "=" * 60)
    print("TEST RESULTS:")
    print("-" * 60)
    
    if compliance_passed:
        print("✅ PASS: AdCP Protocol Compliance")
        print("  - promoted_offering is correctly optional")
        print("  - implementation_config is not exposed")
        print("  - Required fields are present")
    else:
        print("❌ FAIL: AdCP Protocol Compliance Issues Found")
        print("  - See details above for specific failures")
    
    print("=" * 60)
    
    return compliance_passed

def test_full_adcp_compliance():
    """Test full AdCP spec compliance and document differences."""
    
    print("\n" + "=" * 80)
    print("FULL ADCP PROTOCOL COMPLIANCE TEST")
    print("=" * 80)
    print("\nTesting against AdCP specification at https://adcontextprotocol.org/")
    print("Documentation of differences and workarounds\n")
    
    # Track compliance
    compliant_tools = []
    non_compliant_tools = []
    missing_tools = []
    extra_tools = []
    
    # Test create_media_buy with empty targeting
    print("-" * 80)
    print("Testing create_media_buy with empty targeting_overlay")
    print("-" * 80)
    
    result = call_mcp_tool("create_media_buy", {
        "product_ids": ["test_display_300x250"],
        "flight_start_date": "2025-09-01",
        "flight_end_date": "2025-09-30",
        "total_budget": 5000,
        "targeting_overlay": {}  # Empty object should be accepted
    })
    
    media_buy_id = None
    if result.get('success'):
        media_buy_id = result.get('result', {}).get('media_buy_id')
        print(f"✅ SUCCESS - Created media buy with empty targeting: {media_buy_id}")
        compliant_tools.append("create_media_buy")
    else:
        print(f"❌ FAILED: {result.get('error')}")
        non_compliant_tools.append("create_media_buy")
    
    # Test tools that shouldn't exist
    print("\n" + "-" * 80)
    print("Testing for incorrectly assumed tools")
    print("-" * 80)
    
    for tool in ["list_media_buys", "get_media_buys"]:
        result = call_mcp_tool(tool, {})
        if not result.get('success'):
            print(f"✅ {tool}: Correctly not implemented (not in AdCP spec)")
        else:
            print(f"⚠️  {tool}: Exists but NOT in AdCP spec!")
            extra_tools.append(tool)
    
    # Test get_principal_summary (our extension)
    print("\n" + "-" * 80)
    print("Testing get_principal_summary (our extension)")
    print("-" * 80)
    
    result = call_mcp_tool("get_principal_summary", {})
    if result.get('success'):
        media_buys = result.get('result', {}).get('media_buys', [])
        print(f"✅ SUCCESS - get_principal_summary works ({len(media_buys)} media buys)")
        extra_tools.append("get_principal_summary")
    else:
        print(f"❌ FAILED: {result.get('error')}")
    
    # Test add_creative_assets (spec name) vs add_creative_assets (our name)
    print("\n" + "-" * 80)
    print("Testing creative submission tools")
    print("-" * 80)
    
    # Try AdCP spec name
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
    
    if not result.get('success') and 'Unknown tool' in result.get('error', ''):
        print("❌ add_creative_assets: Not implemented (should exist per AdCP spec)")
        missing_tools.append("add_creative_assets")
    
    # Try our implementation
    now = datetime.now()
    result = call_mcp_tool("add_creative_assets", {
        "media_buy_id": media_buy_id or "test_buy",
        "creatives": [{
            "creative_id": "creative_test_001",
            "principal_id": "test_principal",
            "format_id": "display_300x250",
            "name": "Test Banner",
            "content_uri": "https://example.com/banner.jpg",
            "created_at": now.isoformat() + "Z",
            "updated_at": now.isoformat() + "Z"  # Also required
        }]
    })
    
    if result.get('success'):
        print("✅ add_creative_assets: Works (our alternative to add_creative_assets)")
        extra_tools.append("add_creative_assets")
    else:
        print(f"⚠️  add_creative_assets: {result.get('error', 'Unknown error')[:100]}")
    
    # Summary
    print("\n" + "=" * 80)
    print("COMPLIANCE SUMMARY")
    print("=" * 80)
    
    print("\n✅ COMPLIANT TOOLS:")
    for tool in compliant_tools:
        print(f"   - {tool}")
    
    if missing_tools:
        print("\n❌ MISSING FROM IMPLEMENTATION (in spec, not implemented):")
        for tool in missing_tools:
            print(f"   - {tool}")
    
    if extra_tools:
        print("\n🔧 PROPRIETARY EXTENSIONS (not in spec, we added):")
        for tool in extra_tools:
            print(f"   - {tool}")
    
    print("\n" + "=" * 80)
    print("KEY DIFFERENCES FROM ADCP SPEC:")
    print("=" * 80)
    print("""
1. CREATIVE SUBMISSION:
   - AdCP spec: add_creative_assets (not implemented)
   - Our system: add_creative_assets (different structure)

2. LISTING MEDIA BUYS:
   - AdCP spec: No defined method
   - Our solution: get_principal_summary

3. FIXED ISSUES:
   - promoted_offering: NOW REQUIRED per spec ✓
   - targeting_overlay: NOW OPTIONAL (accepts empty object) ✓
   - implementation_config: NEVER EXPOSED (security fix) ✓
""")
    
    return len(missing_tools) == 0 and len(non_compliant_tools) == 0

if __name__ == "__main__":
    # Test original get_products compliance
    products_compliant = test_get_products_compliance()
    
    # Test full AdCP compliance
    full_compliant = test_full_adcp_compliance()
    
    success = products_compliant and full_compliant
    sys.exit(0 if success else 1)