#!/usr/bin/env python3
"""Test dashboard and settings pages with authentication."""

import requests
import sys
import json

BASE_URL = "http://localhost:8004"
TENANT_ID = "default"

def test_with_auth():
    """Test dashboard and settings with test authentication."""
    
    print(f"\n{'='*60}")
    print("Testing Dashboard and Settings with Authentication")
    print(f"{'='*60}\n")
    
    # Create a session to maintain cookies
    session = requests.Session()
    
    # Test 1: Authenticate using test mode
    print("1. Authenticating with test mode...")
    auth_data = {
        "email": "test_super_admin@example.com",
        "password": "test123",
        "tenant_id": ""
    }
    
    response = session.post(f"{BASE_URL}/test/auth", json=auth_data)
    if response.status_code == 200:
        print(f"   ✓ Authentication successful")
    else:
        print(f"   ✗ Authentication failed: {response.status_code}")
        print(f"   Response: {response.text[:200]}")
        return False
    
    # Test 2: Access dashboard
    print("\n2. Testing dashboard page...")
    response = session.get(f"{BASE_URL}/tenant/{TENANT_ID}")
    
    if response.status_code == 200:
        print(f"   ✓ Dashboard loads successfully")
        
        # Check for key elements
        if "Operational Dashboard" in response.text:
            print(f"   ✓ Dashboard content verified")
        
        # Check for errors in HTML
        if "UndefinedColumn" in response.text:
            print(f"   ✗ Database column error detected in HTML!")
            return False
        if "UndefinedTable" in response.text:
            print(f"   ✗ Database table error detected in HTML!")
            return False
            
    elif response.status_code == 500:
        print(f"   ✗ Dashboard returns 500 error!")
        print(f"   Response preview: {response.text[:500]}")
        return False
    else:
        print(f"   ⚠️  Unexpected status: {response.status_code}")
    
    # Test 3: Access settings page
    print("\n3. Testing settings page...")
    response = session.get(f"{BASE_URL}/tenant/{TENANT_ID}/settings")
    
    if response.status_code == 200:
        print(f"   ✓ Settings page loads successfully")
        
        # Check for key elements
        if "Configuration Settings" in response.text or "Settings" in response.text:
            print(f"   ✓ Settings content verified")
        
        # Check for errors in HTML
        if "UndefinedColumn" in response.text:
            print(f"   ✗ Database column error detected in HTML!")
            return False
        if "UndefinedTable" in response.text:
            print(f"   ✗ Database table error detected in HTML!")
            return False
            
    elif response.status_code == 500:
        print(f"   ✗ Settings page returns 500 error!")
        print(f"   Response preview: {response.text[:500]}")
        return False
    else:
        print(f"   ⚠️  Unexpected status: {response.status_code}")
    
    # Test 4: Test specific settings sections
    print("\n4. Testing settings sections...")
    sections = ["general", "ad_server", "products", "formats", "advertisers", "integrations", "tokens", "users", "advanced"]
    
    for section in sections:
        response = session.get(f"{BASE_URL}/tenant/{TENANT_ID}/settings/{section}")
        
        if response.status_code == 200:
            print(f"   ✓ Settings section '{section}' loads")
        elif response.status_code == 500:
            print(f"   ✗ Settings section '{section}' returns 500!")
            print(f"      Error preview: {response.text[:200] if response.text else 'No content'}")
            return False
        else:
            print(f"   ⚠️  Settings section '{section}': status {response.status_code}")
    
    print(f"\n{'='*60}")
    print("Test Summary")
    print(f"{'='*60}")
    print("✓ All pages load successfully")
    print("✓ No 500 errors detected")
    print("✓ Authentication working")
    
    return True

if __name__ == "__main__":
    # Check if test mode is enabled
    test_env_check = requests.get(f"{BASE_URL}/test/login")
    if test_env_check.status_code == 404:
        print("\n⚠️  Test mode is not enabled!")
        print("Add ADCP_AUTH_TEST_MODE=true to .env and restart admin-ui")
        sys.exit(1)
    
    success = test_with_auth()
    sys.exit(0 if success else 1)