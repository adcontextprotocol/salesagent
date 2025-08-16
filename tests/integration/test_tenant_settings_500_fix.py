"""
Integration tests to ensure the tenant settings page doesn't return 500 errors.
These tests were created to prevent regression of the 500 errors that were fixed.
"""

import pytest
from unittest.mock import patch, MagicMock
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from admin_ui import app


@pytest.fixture
def client():
    """Create a test client for the Flask app"""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def mock_db():
    """Mock database connection"""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    
    # Configure mock to return tuples (not dicts) as real DB does
    mock_cursor.fetchone.side_effect = [
        ('default', 'Default Tenant', None, 'mock', '{}', 'free', None, None),  # tenant query
        (0,),  # product count
        (0,),  # active products (now hardcoded, but mock for consistency)
        (0,),  # draft products (now hardcoded, but mock for consistency)
        (0,),  # principals count
        (0,),  # active advertisers
        # creative_formats query returns empty list
    ]
    mock_cursor.fetchall.return_value = []
    
    mock_conn.execute.return_value = mock_cursor
    mock_conn.cursor.return_value = mock_cursor
    
    return mock_conn


@pytest.fixture
def authenticated_session(client):
    """Create an authenticated session using test mode"""
    os.environ['ADCP_AUTH_TEST_MODE'] = 'true'
    
    # Perform test authentication
    response = client.post('/test/auth', data={
        'email': 'test_super_admin@example.com',
        'password': 'test123'
    }, follow_redirects=False)
    
    # Should redirect on successful auth
    assert response.status_code == 302
    
    return client


class TestTenantSettings500Fix:
    """Test suite to ensure tenant settings page doesn't throw 500 errors"""
    
    @patch('admin_ui.get_db_connection')
    @patch('admin_ui.DatabaseConfig.get_db_config')
    def test_settings_page_no_500_with_postgresql(self, mock_get_db_config, mock_get_db, 
                                                  authenticated_session, mock_db):
        """Test that settings page loads without 500 error with PostgreSQL"""
        # Configure for PostgreSQL
        mock_get_db_config.return_value = {'type': 'postgresql'}
        mock_get_db.return_value = mock_db
        
        # Access the settings page
        response = authenticated_session.get('/tenant/default/settings')
        
        # Should not return 500
        assert response.status_code != 500, f"Settings page returned 500 error: {response.data}"
        # Should either be 200 (success) or 302 (redirect to login)
        assert response.status_code in [200, 302]
    
    @patch('admin_ui.get_db_connection')
    @patch('admin_ui.DatabaseConfig.get_db_config')
    def test_settings_page_no_500_with_sqlite(self, mock_get_db_config, mock_get_db,
                                              authenticated_session, mock_db):
        """Test that settings page loads without 500 error with SQLite"""
        # Configure for SQLite
        mock_get_db_config.return_value = {'type': 'sqlite'}
        mock_get_db.return_value = mock_db
        
        # Access the settings page
        response = authenticated_session.get('/tenant/default/settings')
        
        # Should not return 500
        assert response.status_code != 500, f"Settings page returned 500 error: {response.data}"
        # Should either be 200 (success) or 302 (redirect to login)
        assert response.status_code in [200, 302]
    
    @patch('admin_ui.get_db_connection')
    def test_settings_page_handles_missing_columns(self, mock_get_db, authenticated_session):
        """Test that settings page handles missing database columns gracefully"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        # Simulate the fixed queries (no is_active, no auto_approve)
        mock_cursor.fetchone.side_effect = [
            ('default', 'Default Tenant', None, 'mock', '{}', 'free', None, None),
            (5,),  # product count
            (2,),  # principals count  
            (1,),  # active advertisers
        ]
        mock_cursor.fetchall.return_value = [
            ('format_1', 'Display 300x250', 300, 250, 0),
            ('format_2', 'Video 640x480', 640, 480, 0),
        ]
        
        mock_conn.execute.return_value = mock_cursor
        mock_get_db.return_value = mock_conn
        
        response = authenticated_session.get('/tenant/default/settings')
        
        # Should handle gracefully without 500
        assert response.status_code != 500
    
    def test_settings_page_includes_ui_elements(self, authenticated_session):
        """Test that settings page includes the required UI elements"""
        with patch('admin_ui.get_db_connection') as mock_get_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            
            mock_cursor.fetchone.side_effect = [
                ('default', 'Default Tenant', None, 'google_ad_manager', 
                 '{"adapters": {"google_ad_manager": {"enabled": true}}}', 
                 'free', None, None),
                (0,),  # product count
                (0,),  # principals count
                (0,),  # active advertisers
            ]
            mock_cursor.fetchall.return_value = []
            
            mock_conn.execute.return_value = mock_cursor
            mock_get_db.return_value = mock_conn
            
            response = authenticated_session.get('/tenant/default/settings')
            
            if response.status_code == 200:
                # Check for key UI elements
                assert b'Product Setup Wizard' in response.data or \
                       b'products/setup-wizard' in response.data, \
                       "Product Setup Wizard link missing"
                
                assert b'Ad Server' in response.data, \
                       "Ad Server section missing"
                
                assert b'btn-success' in response.data, \
                       "Success button CSS missing"


class TestDashboard500Fix:
    """Test suite to ensure dashboard doesn't throw 500 errors"""
    
    @patch('admin_ui.get_db_connection')
    def test_dashboard_no_500(self, mock_get_db, authenticated_session):
        """Test that dashboard loads without 500 error"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        # Mock all the dashboard queries
        mock_cursor.fetchone.side_effect = [
            ('default', 'Default Tenant', None, 'mock', '{}', 'free', None, None),
            (10,),   # total media buys
            (5,),    # active media buys
            (2500.0,),  # total spend
            (3,),    # pending tasks
            (0,),    # human tasks
        ]
        
        mock_cursor.fetchall.side_effect = [
            # Recent media buys
            [('mb_1', 'principal_1', 'Test Buy', 'active', 1000.0, '2024-01-01')],
            # Recent tasks
            [],
            # Chart data
            [],
        ]
        
        mock_conn.execute.return_value = mock_cursor
        mock_get_db.return_value = mock_conn
        
        response = authenticated_session.get('/tenant/default')
        
        # Should not return 500
        assert response.status_code != 500, f"Dashboard returned 500 error: {response.data}"
        # Should either be 200 (success) or 302 (redirect)
        assert response.status_code in [200, 302]


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, '-v'])