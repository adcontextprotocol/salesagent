#!/usr/bin/env python3
"""
Test authentication mode for Admin UI.

This module provides tests that bypass OAuth for automated UI testing.
Requires ADCP_AUTH_TEST_MODE=true environment variable.
"""

import os
import sys
import requests
from urllib.parse import urljoin
import pytest

# Configuration
DEFAULT_TENANT_ID = "default"


class TestAuthMode:
    """Test suite for authentication mode bypass."""
    
    @pytest.fixture(scope="class")
    def base_url(self):
        """Get base URL from environment or use default."""
        port = os.environ.get('ADMIN_UI_PORT', '8001')
        return f"http://localhost:{port}"
    
    @pytest.fixture(scope="class")
    def session(self):
        """Create a session for maintaining cookies."""
        return requests.Session()
    
    def test_mode_enabled(self):
        """Test that authentication mode is properly enabled."""
        assert os.environ.get('ADCP_AUTH_TEST_MODE', '').lower() == 'true', \
            "ADCP_AUTH_TEST_MODE must be set to 'true'"
    
    def test_test_login_page(self, session, base_url):
        """Test that the test login page is accessible."""
        response = session.get(urljoin(base_url, '/test/login'))
        assert response.status_code == 200
        assert 'TEST MODE' in response.text
        assert 'Test Login' in response.text
    
    def test_super_admin_login(self, session, base_url):
        """Test super admin login flow."""
        # Login
        login_data = {
            'email': 'test_super_admin@example.com',
            'password': 'test123'
        }
        response = session.post(urljoin(base_url, '/test/auth'), 
                               data=login_data, 
                               allow_redirects=False)
        assert response.status_code in [302, 303]
        
        # Verify access to dashboard
        response = session.get(base_url)
        assert response.status_code == 200
        assert 'test_super_admin@example.com' in response.text
        assert 'TEST MODE ACTIVE' in response.text
        
        # Verify can see tenants
        assert 'Default Publisher' in response.text
    
    def test_tenant_admin_login(self, session, base_url):
        """Test tenant admin login flow."""
        # Fresh session
        session = requests.Session()
        
        # Login with tenant_id
        login_data = {
            'email': 'test_tenant_admin@example.com',
            'password': 'test123',
            'tenant_id': DEFAULT_TENANT_ID
        }
        response = session.post(urljoin(base_url, '/test/auth'), 
                               data=login_data, 
                               allow_redirects=False)
        assert response.status_code in [302, 303]
        
        # Should redirect to tenant page
        if 'Location' in response.headers:
            location = response.headers['Location']
            assert f'/tenant/{DEFAULT_TENANT_ID}' in location
    
    def test_operations_dashboard(self, session, base_url):
        """Test access to operations dashboard."""
        # Login first
        login_data = {
            'email': 'test_super_admin@example.com',
            'password': 'test123'
        }
        session.post(urljoin(base_url, '/test/auth'), data=login_data)
        
        # Access operations
        response = session.get(urljoin(base_url, f'/tenant/{DEFAULT_TENANT_ID}/operations'))
        assert response.status_code == 200
        assert 'Media Buys' in response.text
    
    def test_logout(self, session, base_url):
        """Test logout functionality."""
        # Login first
        login_data = {
            'email': 'test_super_admin@example.com',
            'password': 'test123'
        }
        session.post(urljoin(base_url, '/test/auth'), data=login_data)
        
        # Logout
        response = session.get(urljoin(base_url, '/logout'), allow_redirects=False)
        assert response.status_code in [302, 303]
        
        # Verify can't access protected pages
        response = session.get(base_url, allow_redirects=False)
        assert response.status_code in [302, 303] or 'login' in response.headers.get('Location', '')
    
    def test_disabled_returns_404(self):
        """Test that endpoints return 404 when test mode is disabled."""
        # This test would need to run in a separate process with test mode disabled
        # Skipping for now as it requires env manipulation
        pytest.skip("Requires separate process to test disabled mode")


if __name__ == '__main__':
    # Simple standalone test runner
    if os.environ.get('ADCP_AUTH_TEST_MODE', '').lower() != 'true':
        print("❌ Error: ADCP_AUTH_TEST_MODE must be set to 'true'")
        sys.exit(1)
    
    print("Running authentication mode tests...")
    pytest.main([__file__, '-v'])