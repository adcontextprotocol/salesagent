#!/usr/bin/env python3
"""
Test script to verify the UI testing subagent is working.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

# We need to test differently since these are MCP tools
# For now, let's test the functions directly
import ui_test_server

async def test_subagent():
    """Test the subagent tools."""
    print("🧪 Testing UI Testing Subagent\n")
    
    # Test 1: List tests
    print("1. Listing available tests...")
    try:
        tests = await ui_test_server.list_ui_tests()
        print(f"✅ Found {len(tests)} test files")
        for test_file, functions in list(tests.items())[:3]:
            print(f"   - {test_file}: {len(functions)} tests")
    except Exception as e:
        print(f"❌ Failed to list tests: {e}")
    
    print()
    
    # Test 2: Check auth status
    print("2. Checking authentication status...")
    try:
        auth = await ui_test_server.check_auth_status()
        print(f"✅ Auth check complete:")
        print(f"   - Logged in: {auth['logged_in']}")
        print(f"   - Email: {auth.get('email', 'N/A')}")
        print(f"   - Role: {auth.get('role', 'N/A')}")
    except Exception as e:
        print(f"❌ Failed to check auth: {e}")
    
    print()
    
    # Test 3: Generate test code
    print("3. Generating sample test code...")
    try:
        code = await ui_test_server.generate_ui_test(
            feature_description="verify admin can view all tenants",
            test_type="smoke",
            page_objects=["TenantPage"]
        )
        print("✅ Generated test code:")
        print("   " + "\n   ".join(code.split("\n")[:10]) + "...")
    except Exception as e:
        print(f"❌ Failed to generate test: {e}")
    
    print()
    
    # Test 4: Run a simple test
    print("4. Running a basic test...")
    try:
        result = await ui_test_server.run_ui_test(
            "tests/test_basic_setup.py::TestBasicSetup::test_browser_launches",
            headed=False,
            timeout=30
        )
        print(f"✅ Test execution complete:")
        print(f"   - Success: {result['success']}")
        print(f"   - Exit code: {result['exit_code']}")
        if result['screenshots']:
            print(f"   - Screenshots captured: {len(result['screenshots'])}")
    except Exception as e:
        print(f"❌ Failed to run test: {e}")
    
    print("\n✨ Subagent testing complete!")

if __name__ == "__main__":
    # Change to UI tests directory
    import os
    os.chdir(Path(__file__).parent.parent)
    
    # Run tests
    asyncio.run(test_subagent())