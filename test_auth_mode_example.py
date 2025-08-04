#!/usr/bin/env python3
"""
Example test script demonstrating the UI test mode for automated testing.

This script shows how to:
1. Enable test mode via environment variable
2. Login using test credentials
3. Perform automated UI testing without OAuth

IMPORTANT: This is for testing only. Never use in production!
"""

import os
import requests
from urllib.parse import urljoin

# Configuration
BASE_URL = "http://localhost:8001"
TEST_TENANT_ID = "test_tenant_123"

def test_auth_mode():
    """Demonstrate test authentication mode."""
    
    # Check if test mode is enabled
    if os.environ.get('ADCP_AUTH_TEST_MODE', '').lower() != 'true':
        print("❌ Test mode is not enabled!")
        print("   Set ADCP_AUTH_TEST_MODE=true to enable test authentication")
        return
    
    print("✅ Test mode is enabled")
    
    # Create a session to maintain cookies
    session = requests.Session()
    
    # Test 1: Login as super admin
    print("\n1. Testing super admin login...")
    login_data = {
        'email': 'test_super_admin@example.com',
        'password': 'test123'
    }
    
    response = session.post(urljoin(BASE_URL, '/test/auth'), data=login_data)
    if response.status_code == 200:
        print("   ✅ Super admin login successful")
        # The session now has authentication cookies
        
        # Verify we can access protected pages
        response = session.get(urljoin(BASE_URL, '/'))
        if 'AdCP Sales Agent Admin' in response.text and 'test_super_admin@example.com' in response.text:
            print("   ✅ Can access admin dashboard")
        else:
            print("   ❌ Cannot access admin dashboard")
    else:
        print(f"   ❌ Login failed: {response.status_code}")
    
    # Logout
    session.get(urljoin(BASE_URL, '/logout'))
    print("   ✅ Logged out")
    
    # Test 2: Login as tenant admin
    print("\n2. Testing tenant admin login...")
    login_data = {
        'email': 'test_tenant_admin@example.com',
        'password': 'test123',
        'tenant_id': TEST_TENANT_ID
    }
    
    response = session.post(urljoin(BASE_URL, '/test/auth'), data=login_data)
    if response.status_code == 200:
        print("   ✅ Tenant admin login successful")
        
        # Verify we can access tenant pages
        response = session.get(urljoin(BASE_URL, f'/tenant/{TEST_TENANT_ID}'))
        if response.status_code == 200:
            print("   ✅ Can access tenant dashboard")
        else:
            print("   ❌ Cannot access tenant dashboard")
    else:
        print(f"   ❌ Login failed: {response.status_code}")
    
    # Test 3: Direct test login page
    print("\n3. Testing dedicated test login page...")
    response = session.get(urljoin(BASE_URL, '/test/login'))
    if response.status_code == 200 and 'TEST MODE' in response.text:
        print("   ✅ Test login page accessible")
    else:
        print("   ❌ Test login page not accessible")
    
    print("\n✅ Test authentication demo complete!")
    print("\nFor automated testing (e.g., with Selenium):")
    print("1. Set ADCP_AUTH_TEST_MODE=true")
    print("2. Navigate to /test/login for a simple form")
    print("3. Or POST directly to /test/auth with credentials")

if __name__ == '__main__':
    test_auth_mode()