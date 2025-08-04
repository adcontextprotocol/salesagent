#!/usr/bin/env python3
"""
Example Selenium test showing how to use test authentication mode for browser automation.

Prerequisites:
    pip install selenium

This demonstrates automated browser testing without dealing with OAuth flows.
"""

import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

# Configuration
BASE_URL = "http://localhost:8001"
TEST_TENANT_ID = "test_tenant_123"  # Replace with an actual tenant ID

def test_with_selenium():
    """Demonstrate automated browser testing with test mode."""
    
    # Check test mode
    if os.environ.get('ADCP_AUTH_TEST_MODE', '').lower() != 'true':
        print("❌ Error: ADCP_AUTH_TEST_MODE must be set to 'true'")
        print("   Run: export ADCP_AUTH_TEST_MODE=true")
        return
    
    # Initialize Chrome driver (you may need to install ChromeDriver)
    driver = webdriver.Chrome()
    wait = WebDriverWait(driver, 10)
    
    try:
        print("🧪 Starting Selenium test with test authentication mode...\n")
        
        # Test 1: Super Admin Login
        print("1. Testing super admin login flow...")
        driver.get(f"{BASE_URL}/login")
        
        # Verify test mode is visible
        assert "TEST MODE ENABLED" in driver.page_source, "Test mode banner not visible"
        print("   ✅ Test mode banner visible")
        
        # Find and fill test login form
        email_select = Select(driver.find_element(By.NAME, "email"))
        email_select.select_by_value("test_super_admin@example.com")
        
        password_field = driver.find_element(By.NAME, "password")
        password_field.clear()
        password_field.send_keys("test123")
        
        # Submit form
        submit_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        submit_button.click()
        
        # Wait for redirect and verify login
        wait.until(EC.presence_of_element_located((By.LINK_TEXT, "Logout")))
        print("   ✅ Successfully logged in as super admin")
        
        # Verify we can see tenant list
        assert "Tenants" in driver.page_source
        print("   ✅ Can access tenant management")
        
        # Logout
        logout_link = driver.find_element(By.LINK_TEXT, "Logout")
        logout_link.click()
        print("   ✅ Logged out\n")
        
        # Test 2: Tenant Admin Login
        print("2. Testing tenant admin login flow...")
        driver.get(f"{BASE_URL}/tenant/{TEST_TENANT_ID}/login")
        
        # Use test form for tenant login
        email_select = Select(driver.find_element(By.NAME, "email"))
        email_select.select_by_value("test_tenant_admin@example.com")
        
        password_field = driver.find_element(By.NAME, "password")
        password_field.clear()
        password_field.send_keys("test123")
        
        submit_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        submit_button.click()
        
        # Wait for redirect
        wait.until(EC.url_contains(f"/tenant/{TEST_TENANT_ID}"))
        print("   ✅ Successfully logged in as tenant admin")
        
        # Verify tenant access
        assert TEST_TENANT_ID in driver.current_url
        print("   ✅ Can access tenant dashboard")
        
        # Test 3: Direct test login page
        print("\n3. Testing dedicated test login page...")
        driver.get(f"{BASE_URL}/test/login")
        
        assert "Test Login" in driver.page_source
        assert "Available Test Users" in driver.page_source
        print("   ✅ Test login page accessible with user list")
        
        print("\n✅ All Selenium tests passed!")
        print("\n📝 Summary:")
        print("   - Test mode allows bypassing OAuth for automation")
        print("   - Clear visual indicators show test mode is active")
        print("   - Multiple test users available for different roles")
        print("   - Perfect for CI/CD pipelines and automated testing")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        # Take screenshot for debugging
        driver.save_screenshot("test_failure.png")
        print("   Screenshot saved as test_failure.png")
        raise
    
    finally:
        # Clean up
        driver.quit()

def test_api_endpoints():
    """Test programmatic access using test authentication."""
    import requests
    
    print("\n4. Testing programmatic API access...")
    
    session = requests.Session()
    
    # Login via API
    response = session.post(f"{BASE_URL}/test/auth", data={
        'email': 'test_super_admin@example.com',
        'password': 'test123'
    })
    
    if response.status_code == 200:
        print("   ✅ API login successful")
        
        # Test API endpoints
        response = session.get(f"{BASE_URL}/api/tenants")
        if response.status_code == 200:
            print("   ✅ Can access API endpoints")
            tenants = response.json()
            print(f"   ✅ Found {len(tenants)} tenants")
    else:
        print("   ❌ API login failed")

if __name__ == '__main__':
    print("AdCP Admin UI - Test Mode Demo")
    print("==============================\n")
    
    # Run Selenium tests
    test_with_selenium()
    
    # Run API tests
    test_api_endpoints()
    
    print("\n🎉 Test mode demonstration complete!")
    print("\n⚠️  Remember: NEVER enable test mode in production!")