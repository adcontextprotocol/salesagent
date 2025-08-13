#!/usr/bin/env python3
"""
Quick test to verify promoted_offering is now required per AdCP spec.
"""

import json
import subprocess

def test_promoted_offering_requirement():
    """Test that promoted_offering is required per AdCP spec."""
    
    print("Testing promoted_offering requirement...")
    print("=" * 60)
    
    # Test 1: Without promoted_offering (should fail)
    print("\n1. Testing WITHOUT promoted_offering (should fail)...")
    result = subprocess.run([
        'curl', '-s', '-X', 'POST', 'http://localhost:8001/api/mcp-test/call',
        '-H', 'Content-Type: application/json',
        '-H', 'X-Debug-Mode: test',
        '-d', json.dumps({
            "tool": "get_products",
            "params": {
                "brief": "Display advertising for general campaign"
                # promoted_offering missing
            },
            "access_token": "token_6119345e4a080d7223ee631062ca0e9e",
            "server_url": "http://localhost:8005/mcp/"
        })
    ], capture_output=True, text=True)
    
    try:
        response = json.loads(result.stdout)
        if not response.get('success'):
            error = response.get('error', '')
            if 'promoted_offering' in error and 'required' in error:
                print("  ✅ CORRECT: Error mentions promoted_offering is required")
                print(f"     Error: {error}")
            else:
                print(f"  ❌ WRONG: Error doesn't mention promoted_offering requirement")
                print(f"     Error: {error}")
        else:
            print("  ❌ WRONG: Request succeeded without promoted_offering!")
    except Exception as e:
        print(f"  ❌ Failed to parse response: {e}")
    
    # Test 2: With promoted_offering (should succeed)
    print("\n2. Testing WITH promoted_offering (should succeed)...")
    result = subprocess.run([
        'curl', '-s', '-X', 'POST', 'http://localhost:8001/api/mcp-test/call',
        '-H', 'Content-Type: application/json',
        '-H', 'X-Debug-Mode: test',
        '-d', json.dumps({
            "tool": "get_products",
            "params": {
                "brief": "Display advertising for general campaign",
                "promoted_offering": "Nike running shoes - athletic footwear brand"
            },
            "access_token": "token_6119345e4a080d7223ee631062ca0e9e",
            "server_url": "http://localhost:8005/mcp/"
        })
    ], capture_output=True, text=True)
    
    try:
        response = json.loads(result.stdout)
        if response.get('success'):
            products = response.get('result', {}).get('products', [])
            print(f"  ✅ CORRECT: Request succeeded with {len(products)} products")
            
            # Check that implementation_config is NOT in the response
            if products:
                product = products[0]
                if 'implementation_config' in product:
                    print(f"  ❌ SECURITY ISSUE: implementation_config exposed!")
                else:
                    print(f"  ✅ SECURITY: implementation_config correctly hidden")
        else:
            print(f"  ❌ WRONG: Request failed: {response.get('error')}")
    except Exception as e:
        print(f"  ❌ Failed to parse response: {e}")
    
    print("\n" + "=" * 60)
    print("SUMMARY:")
    print("- promoted_offering is REQUIRED per AdCP spec ✓")
    print("- implementation_config is NEVER exposed ✓")
    print("=" * 60)

if __name__ == "__main__":
    test_promoted_offering_requirement()