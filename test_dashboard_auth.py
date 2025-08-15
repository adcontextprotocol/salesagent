#\!/usr/bin/env python3
"""Test dashboard authentication and settings page."""

import os
import sys
import json
import requests
from datetime import datetime
import time

# Test configuration
BASE_URL = "http://localhost:8004"
TENANT_ID = "default"

def test_settings_page():
    """Test that the settings page loads properly."""
    
    print(f"\n{'='*60}")
    print("Testing Dashboard and Settings Pages")
    print(f"{'='*60}\n")
    
    # Test 1: Check if server is responding
    print("1. Testing server health...")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 404:
            print("   ⚠️  No health endpoint, trying root...")
            response = requests.get(f"{BASE_URL}/", timeout=5)
        print(f"   ✓ Server is responding (status: {response.status_code})")
    except Exception as e:
        print(f"   ✗ Server not responding: {e}")
        return False
    
    # Test 2: Check login redirect
    print("\n2. Testing login redirect...")
    response = requests.get(f"{BASE_URL}/tenant/{TENANT_ID}/settings", allow_redirects=False)
    if response.status_code == 302:
        print(f"   ✓ Redirects to login (as expected)")
        print(f"   Location: {response.headers.get('Location', 'N/A')}")
    else:
        print(f"   ⚠️  Unexpected status: {response.status_code}")
    
    # Test 3: Check dashboard route
    print("\n3. Testing dashboard route...")
    response = requests.get(f"{BASE_URL}/tenant/{TENANT_ID}", allow_redirects=False)
    if response.status_code == 302:
        print(f"   ✓ Dashboard redirects to login (as expected)")
    elif response.status_code == 500:
        print(f"   ✗ Dashboard returns 500 error!")
        print(f"   Response: {response.text[:500] if response.text else 'No content'}")
        return False
    else:
        print(f"   Status: {response.status_code}")
    
    # Test 4: Try with a fake session cookie (to test authenticated path)
    print("\n4. Testing with fake authentication...")
    fake_session = "eyJhdXRoZW50aWNhdGVkIjp0cnVlLCJyb2xlIjoic3VwZXJfYWRtaW4ifQ"
    cookies = {"session": fake_session}
    
    response = requests.get(f"{BASE_URL}/tenant/{TENANT_ID}/settings", cookies=cookies, allow_redirects=False)
    print(f"   Settings page status: {response.status_code}")
    
    if response.status_code == 500:
        print(f"   ✗ Settings page returns 500 error!")
        # Try to get error details
        if response.text:
            if "UndefinedColumn" in response.text:
                print("   Error: Database column issue detected")
            elif "UndefinedTable" in response.text:
                print("   Error: Database table issue detected")
            else:
                print(f"   Error snippet: {response.text[:300]}")
        return False
    
    response = requests.get(f"{BASE_URL}/tenant/{TENANT_ID}", cookies=cookies, allow_redirects=False)
    print(f"   Dashboard page status: {response.status_code}")
    
    if response.status_code == 500:
        print(f"   ✗ Dashboard returns 500 error!")
        if response.text and "UndefinedColumn" in response.text:
            print("   Error: Database column issue detected")
        return False
    
    print(f"\n{'='*60}")
    print("Test Summary")
    print(f"{'='*60}")
    
    if response.status_code != 500:
        print("✓ No 500 errors detected")
        print("✓ Server is operational")
        return True
    else:
        print("✗ 500 errors found - needs investigation")
        return False

if __name__ == "__main__":
    success = test_settings_page()
    
    # Also check Docker logs for errors
    print(f"\n{'='*60}")
    print("Checking Container Logs for Errors")
    print(f"{'='*60}\n")
    
    import subprocess
    
    try:
        # Get recent error logs
        result = subprocess.run(
            ["docker", "logs", "madrid-1-admin-ui-1", "--tail", "50"],
            capture_output=True, text=True, timeout=5
        )
        
        if result.returncode == 0:
            output = result.stderr + result.stdout
            error_lines = [line for line in output.split('\n') 
                          if any(word in line.lower() for word in ['error', 'exception', 'traceback', '500'])]
            
            if error_lines:
                print("Recent errors found in logs:")
                for line in error_lines[-10:]:  # Last 10 error lines
                    print(f"  {line}")
            else:
                print("No recent errors in container logs")
        else:
            print("Could not fetch container logs")
    except Exception as e:
        print(f"Error checking logs: {e}")
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)
