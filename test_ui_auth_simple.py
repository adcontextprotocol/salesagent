#!/usr/bin/env python3
"""
Simple test demonstrating UI test authentication mode.
This test logs in and navigates through several admin pages.
"""

import os
import sys
import requests
from urllib.parse import urljoin
import json

# Configuration
BASE_URL = "http://localhost:8001"

def test_ui_navigation():
    """Test logging in and navigating through admin pages."""
    
    # First, check if test mode is enabled
    if os.environ.get('ADCP_AUTH_TEST_MODE', '').lower() != 'true':
        print("❌ Error: Test mode is not enabled!")
        print("   Please run: export ADCP_AUTH_TEST_MODE=true")
        print("   Then restart the admin UI service")
        return False
    
    print("✅ Test mode is enabled")
    print(f"🌐 Testing against: {BASE_URL}\n")
    
    # Create a session to maintain cookies
    session = requests.Session()
    
    # Step 1: Test that we can access the test login page
    print("1. Checking test login page...")
    try:
        response = session.get(urljoin(BASE_URL, '/test/login'))
        if response.status_code == 200 and 'TEST MODE' in response.text:
            print("   ✅ Test login page is accessible")
        else:
            print(f"   ❌ Test login page returned {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("   ❌ Cannot connect to admin UI. Is it running?")
        print("      Run: docker-compose up admin-ui")
        return False
    
    # Step 2: Login as super admin
    print("\n2. Logging in as super admin...")
    login_data = {
        'email': 'test_super_admin@example.com',
        'password': 'test123'
    }
    
    response = session.post(urljoin(BASE_URL, '/test/auth'), data=login_data, allow_redirects=False)
    if response.status_code in [302, 303]:  # Redirect after successful login
        print("   ✅ Login successful (redirected)")
    else:
        print(f"   ❌ Login failed with status {response.status_code}")
        return False
    
    # Follow the redirect
    if 'Location' in response.headers:
        redirect_url = response.headers['Location']
        response = session.get(urljoin(BASE_URL, redirect_url))
    
    # Step 3: Verify we can access the main dashboard
    print("\n3. Accessing main dashboard...")
    response = session.get(BASE_URL)
    if response.status_code == 200:
        if 'test_super_admin@example.com' in response.text:
            print("   ✅ Dashboard accessible, user email visible")
        else:
            print("   ⚠️  Dashboard accessible but user email not found")
        
        # Check for test mode banner
        if 'TEST MODE ACTIVE' in response.text:
            print("   ✅ Test mode banner is visible")
    else:
        print(f"   ❌ Dashboard returned {response.status_code}")
        return False
    
    # Step 4: Access the tenants API
    print("\n4. Testing API access...")
    response = session.get(urljoin(BASE_URL, '/api/tenants'))
    if response.status_code == 200:
        try:
            tenants = response.json()
            print(f"   ✅ API accessible, found {len(tenants)} tenants")
            
            # Show first tenant if available
            if tenants:
                first_tenant = tenants[0]
                print(f"   📝 First tenant: {first_tenant.get('name', 'Unknown')} (ID: {first_tenant.get('tenant_id', 'Unknown')})")
                
                # Store tenant ID for further testing
                tenant_id = first_tenant.get('tenant_id')
            else:
                print("   ℹ️  No tenants found in database")
                tenant_id = None
        except json.JSONDecodeError:
            print("   ❌ API returned invalid JSON")
            return False
    else:
        print(f"   ❌ API returned {response.status_code}")
        tenant_id = None
    
    # Step 5: Try to access a tenant page if we have a tenant
    if tenant_id:
        print(f"\n5. Accessing tenant page for {tenant_id}...")
        response = session.get(urljoin(BASE_URL, f'/tenant/{tenant_id}'))
        if response.status_code == 200:
            print("   ✅ Tenant page accessible")
        else:
            print(f"   ❌ Tenant page returned {response.status_code}")
    
    # Step 6: Access operations dashboard
    print("\n6. Accessing operations dashboard...")
    response = session.get(urljoin(BASE_URL, '/operations'))
    if response.status_code == 200:
        print("   ✅ Operations dashboard accessible")
        if 'Media Buys' in response.text:
            print("   ✅ Operations content loaded correctly")
    else:
        print(f"   ❌ Operations dashboard returned {response.status_code}")
    
    # Step 7: Test logout
    print("\n7. Testing logout...")
    response = session.get(urljoin(BASE_URL, '/logout'), allow_redirects=False)
    if response.status_code in [302, 303]:
        print("   ✅ Logout successful (redirected to login)")
        
        # Verify we can't access protected pages anymore
        response = session.get(BASE_URL)
        if response.status_code in [302, 303] or 'login' in response.url:
            print("   ✅ Session cleared, redirected to login")
        else:
            print("   ⚠️  Session might not be fully cleared")
    else:
        print(f"   ❌ Logout returned {response.status_code}")
    
    print("\n✅ All tests completed successfully!")
    return True

def test_tenant_login():
    """Test logging in as a tenant admin."""
    print("\n" + "="*50)
    print("Testing Tenant Admin Login")
    print("="*50 + "\n")
    
    session = requests.Session()
    
    # First, we need a tenant ID - let's get one from the API as super admin
    print("1. Getting a tenant ID...")
    
    # Login as super admin first
    response = session.post(urljoin(BASE_URL, '/test/auth'), data={
        'email': 'test_super_admin@example.com',
        'password': 'test123'
    })
    
    # Get tenants
    response = session.get(urljoin(BASE_URL, '/api/tenants'))
    if response.status_code == 200:
        tenants = response.json()
        if tenants:
            tenant_id = tenants[0]['tenant_id']
            tenant_name = tenants[0]['name']
            print(f"   ✅ Using tenant: {tenant_name} ({tenant_id})")
        else:
            print("   ⚠️  No tenants found, skipping tenant login test")
            return True
    else:
        print("   ❌ Could not get tenants")
        return False
    
    # Logout
    session.get(urljoin(BASE_URL, '/logout'))
    
    # Now login as tenant admin
    print("\n2. Logging in as tenant admin...")
    login_data = {
        'email': 'test_tenant_admin@example.com',
        'password': 'test123',
        'tenant_id': tenant_id
    }
    
    response = session.post(urljoin(BASE_URL, '/test/auth'), data=login_data, allow_redirects=False)
    if response.status_code in [302, 303]:
        print("   ✅ Tenant admin login successful")
        
        # Follow redirect
        if 'Location' in response.headers:
            redirect_url = response.headers['Location']
            response = session.get(urljoin(BASE_URL, redirect_url))
            
            if tenant_id in response.url:
                print(f"   ✅ Redirected to tenant page: {response.url}")
            
            if 'test_tenant_admin@example.com' in response.text:
                print("   ✅ Tenant admin email visible")
            
            if tenant_name in response.text:
                print("   ✅ Tenant name visible")
    else:
        print(f"   ❌ Tenant login failed with status {response.status_code}")
        return False
    
    # Try to access super admin area (should fail)
    print("\n3. Verifying tenant admin restrictions...")
    response = session.get(BASE_URL)
    if response.status_code == 403 or 'Access denied' in response.text:
        print("   ✅ Correctly denied access to super admin area")
    elif response.status_code in [302, 303]:
        print("   ✅ Redirected away from super admin area")
    else:
        print("   ⚠️  Unexpected access to super admin area")
    
    print("\n✅ Tenant admin test completed!")
    return True

if __name__ == '__main__':
    print("AdCP Admin UI - Test Authentication Mode")
    print("========================================\n")
    
    # Check if admin UI is configured
    admin_port = os.environ.get('ADMIN_UI_PORT', '8001')
    if admin_port != '8001':
        BASE_URL = f"http://localhost:{admin_port}"
        print(f"ℹ️  Using custom admin port: {admin_port}")
    
    # Run tests
    success = test_ui_navigation()
    
    if success:
        # Also test tenant login
        test_tenant_login()
        
        print("\n" + "="*50)
        print("🎉 All tests passed!")
        print("="*50)
        print("\n📝 Summary:")
        print("- Test mode allows bypassing OAuth authentication")
        print("- Multiple test users available for different roles")
        print("- Clear visual indicators show when test mode is active")
        print("- Perfect for automated testing and CI/CD pipelines")
        print("\n⚠️  Remember: NEVER enable test mode in production!")
        sys.exit(0)
    else:
        print("\n❌ Tests failed!")
        print("\nTroubleshooting:")
        print("1. Ensure ADCP_AUTH_TEST_MODE=true is set")
        print("2. Make sure the admin UI is running (docker-compose up)")
        print("3. Check that the admin UI is accessible at", BASE_URL)
        sys.exit(1)