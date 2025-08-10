#!/usr/bin/env python3
"""
UI tests for GAM Line Item Viewer.

Tests the UI routes and JavaScript functionality.
Requires ADCP_AUTH_TEST_MODE=true for authentication bypass.
"""

import os
import pytest
import requests
from urllib.parse import urljoin


class TestGAMLineItemViewerUI:
    """Test suite for GAM Line Item Viewer UI."""
    
    @pytest.fixture(scope="class")
    def base_url(self):
        """Get base URL from environment or use default."""
        port = os.environ.get('ADMIN_UI_PORT', '8001')
        return f"http://localhost:{port}"
    
    @pytest.fixture(scope="class")
    def session(self):
        """Create a session for maintaining cookies."""
        return requests.Session()
    
    @pytest.fixture(autouse=True)
    def authenticate(self, session, base_url):
        """Authenticate as super admin before each test."""
        if os.environ.get('ADCP_AUTH_TEST_MODE', '').lower() != 'true':
            pytest.skip("ADCP_AUTH_TEST_MODE not enabled")
        
        login_data = {
            'email': 'test_super_admin@example.com',
            'password': 'test123'
        }
        response = session.post(
            urljoin(base_url, '/test/auth'),
            data=login_data,
            allow_redirects=False
        )
        assert response.status_code in [302, 303], "Authentication failed"
    
    def test_line_item_viewer_page_loads(self, session, base_url):
        """Test that the line item viewer page loads successfully."""
        # Use a known line item ID from test data
        line_item_id = '7046143587'
        tenant_id = 'default'
        
        url = f"{base_url}/tenant/{tenant_id}/gam/line-item/{line_item_id}"
        response = session.get(url)
        
        assert response.status_code == 200
        assert 'GAM Line Item Viewer' in response.text
        assert line_item_id in response.text
        
        # Check that all tabs are present
        assert 'Overview' in response.text
        assert 'Targeting' in response.text
        assert 'Creatives' in response.text
        assert 'Delivery Settings' in response.text
        assert 'Raw GAM Data' in response.text
        assert 'Product JSON' in response.text
    
    def test_line_item_viewer_javascript_functions(self, session, base_url):
        """Test that required JavaScript functions are present."""
        line_item_id = '7046143587'
        tenant_id = 'default'
        
        url = f"{base_url}/tenant/{tenant_id}/gam/line-item/{line_item_id}"
        response = session.get(url)
        
        # Check for required JavaScript functions
        assert 'function loadLineItem()' in response.text
        assert 'function displayLineItemData' in response.text
        assert 'function escapeHtml' in response.text
        assert 'function displayBasicInfo' in response.text
        assert 'function displayOrderInfo' in response.text
        assert 'function displayPricingInfo' in response.text
        assert 'function displayTargeting' in response.text
        assert 'function displayCreatives' in response.text
        assert 'function displayDeliverySettings' in response.text
        
        # Check that debug functions are removed
        assert 'function debugFetch' not in response.text
        assert 'Debug Fetch' not in response.text
        assert 'console.log' not in response.text
    
    def test_api_endpoint_with_auth(self, session, base_url):
        """Test that the API endpoint requires authentication."""
        # Create a new session without authentication
        unauth_session = requests.Session()
        
        url = f"{base_url}/api/tenant/default/gam/line-item/7046143587"
        response = unauth_session.get(url, allow_redirects=False)
        
        # Should redirect to login or return 401/403
        assert response.status_code in [302, 401, 403]
    
    def test_api_endpoint_response_structure(self, session, base_url):
        """Test the structure of the API response."""
        url = f"{base_url}/api/tenant/default/gam/line-item/7046143587"
        response = session.get(url)
        
        # Skip if GAM is not configured
        if response.status_code == 400:
            data = response.json()
            if 'GAM not enabled' in data.get('error', ''):
                pytest.skip("GAM not configured for test tenant")
        
        if response.status_code == 200:
            data = response.json()
            
            # Check required fields
            assert 'line_item' in data
            assert 'order' in data
            assert 'creatives' in data
            assert 'creative_associations' in data
            assert 'media_product_json' in data
            
            # Check media_product_json structure
            product = data['media_product_json']
            assert 'product_id' in product
            assert 'name' in product
            assert 'formats' in product
            assert 'targeting_overlay' in product
            assert 'implementation_config' in product
    
    def test_orders_browser_integration(self, session, base_url):
        """Test that line item viewer is accessible from orders browser."""
        url = f"{base_url}/tenant/default/orders"
        response = session.get(url)
        
        if response.status_code == 200:
            # Check for quick search functionality
            assert 'Quick Line Item Search' in response.text
            assert 'searchLineItem' in response.text
            
            # Check that line items have Details links
            # (This would need actual line items in the test database)
    
    def test_invalid_line_item_error_handling(self, session, base_url):
        """Test error handling for invalid line item IDs."""
        invalid_ids = ['abc', '-123', '0', '999999999999']
        tenant_id = 'default'
        
        for invalid_id in invalid_ids:
            url = f"{base_url}/api/tenant/{tenant_id}/gam/line-item/{invalid_id}"
            response = session.get(url)
            
            # Should return an error
            assert response.status_code in [400, 404]
            
            if response.status_code == 400:
                data = response.json()
                assert 'error' in data
                assert 'Invalid' in data['error'] or 'must be' in data['error']


if __name__ == '__main__':
    # Run with test mode enabled
    os.environ['ADCP_AUTH_TEST_MODE'] = 'true'
    pytest.main([__file__, '-v'])