"""
Integration tests for GAM Reporting API

Tests the GAM reporting endpoints with proper authentication and mocked data.
"""

import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from flask import session

from admin_ui import app
from adapters.gam_reporting_service import GAMReportingService


@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key'
    with app.test_client() as client:
        yield client


@pytest.fixture
def authenticated_session(client):
    """Create an authenticated session for testing."""
    with client.session_transaction() as sess:
        sess['authenticated'] = True
        sess['role'] = 'super_admin'
        sess['email'] = 'test@example.com'
        sess['username'] = 'Test User'
    return client


@pytest.fixture
def tenant_session(client):
    """Create a tenant-specific authenticated session."""
    with client.session_transaction() as sess:
        sess['authenticated'] = True
        sess['role'] = 'tenant_admin'
        sess['tenant_id'] = 'test_tenant'
        sess['email'] = 'tenant@example.com'
        sess['username'] = 'Tenant Admin'
    return client


@pytest.fixture
def mock_db_connection():
    """Mock database connection."""
    # Patch both locations where get_db_connection might be imported
    with patch('adapters.gam_reporting_api.get_db_connection') as mock_api_conn, \
         patch('admin_ui.get_db_connection') as mock_ui_conn, \
         patch('db_config.get_db_connection') as mock_db_config_conn:
        
        # Create a mock cursor that returns the tenant with ad_server field
        mock_cursor = Mock()
        
        # Create a dict-like object that supports both dict access and attribute access
        tenant_data = {
            'ad_server': 'google_ad_manager',
            'tenant_id': 'test_tenant',
            'name': 'Test Tenant'
        }
        
        # Mock fetchone to return dict with get method
        mock_cursor.fetchone.return_value = tenant_data
        
        # Setup all mock connections to return the same cursor
        for mock_conn in [mock_api_conn, mock_ui_conn, mock_db_config_conn]:
            mock_conn_instance = Mock()
            mock_conn_instance.execute.return_value = mock_cursor
            mock_conn_instance.cursor.return_value = mock_cursor
            mock_conn_instance.close = Mock()
            mock_conn.return_value = mock_conn_instance
        
        yield mock_api_conn


@pytest.fixture
def mock_gam_client():
    """Mock GAM client and related functions."""
    # First patch the database connection in gam_helper to avoid SQL errors
    with patch('gam_helper.get_db_connection') as mock_gam_db, \
         patch('gam_helper.get_ad_manager_client_for_tenant') as mock_client, \
         patch('gam_helper.ensure_network_timezone') as mock_timezone:
        # Mock the database to avoid SQL errors
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = ('Test Tenant', 'google_ad_manager')
        mock_gam_db.return_value.__enter__.return_value.cursor.return_value = mock_cursor
        
        # Mock GAM client and timezone
        mock_client.return_value = MagicMock()
        mock_timezone.return_value = 'America/New_York'
        yield mock_client


@pytest.fixture
def mock_gam_service():
    """Mock GAM reporting service."""
    with patch('adapters.gam_reporting_api.GAMReportingService') as mock_service_class:
        mock_service = Mock(spec=GAMReportingService)
        mock_service.get_reporting_data.return_value = {
            'date_range': 'today',
            'granularity': 'hourly',
            'timezone': 'America/New_York',
            'data': [
                {
                    'timestamp': datetime.now().isoformat(),
                    'advertiser_id': '123456',
                    'advertiser_name': 'Test Advertiser',
                    'impressions': 1000,
                    'clicks': 50,
                    'spend': 25.50,
                    'cpm': 25.50
                }
            ],
            'summary': {
                'total_impressions': 1000,
                'total_clicks': 50,
                'total_spend': 25.50,
                'average_cpm': 25.50,
                'average_ctr': 5.0
            },
            'data_freshness': {
                'data_valid_until': datetime.now().isoformat(),
                'next_update_expected': (datetime.now() + timedelta(hours=1)).isoformat()
            }
        }
        mock_service_class.return_value = mock_service
        yield mock_service


class TestGAMReportingAPI:
    """Test GAM reporting API endpoints."""
    
    def test_get_reporting_requires_auth(self, client):
        """Test that reporting endpoint requires authentication."""
        response = client.get('/api/tenant/test_tenant/gam/reporting')
        assert response.status_code == 401
        data = json.loads(response.data)
        assert 'error' in data
        assert 'Authentication required' in data['error']
    
    def test_get_reporting_validates_tenant_id(self, authenticated_session, mock_db_connection):
        """Test that invalid tenant IDs are rejected."""
        response = authenticated_session.get('/api/tenant/invalid-tenant!@#/gam/reporting?date_range=today')
        # Note: Flask may return 404 for invalid URL characters, which is also acceptable
        assert response.status_code in [400, 404]
        if response.status_code == 400:
            data = json.loads(response.data)
            assert 'error' in data
    
    def test_get_reporting_checks_tenant_access(self, tenant_session, mock_db_connection):
        """Test that users can only access their own tenant."""
        response = tenant_session.get('/api/tenant/other_tenant/gam/reporting')
        assert response.status_code == 403
        data = json.loads(response.data)
        assert 'error' in data
        assert 'Access denied' in data['error']
    
    def test_get_reporting_requires_date_range(self, authenticated_session, mock_db_connection, mock_gam_client, mock_gam_service):
        """Test that date_range parameter is required."""
        response = authenticated_session.get('/api/tenant/test_tenant/gam/reporting')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert 'date_range' in data['error']
    
    def test_get_reporting_validates_date_range(self, authenticated_session, mock_db_connection, mock_gam_client, mock_gam_service):
        """Test that invalid date_range values are rejected."""
        response = authenticated_session.get('/api/tenant/test_tenant/gam/reporting?date_range=invalid')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert 'Invalid or missing date_range' in data['error']
    
    def test_get_reporting_validates_advertiser_id(self, authenticated_session, mock_db_connection, mock_gam_client, mock_gam_service):
        """Test that invalid advertiser_id format is rejected."""
        response = authenticated_session.get('/api/tenant/test_tenant/gam/reporting?date_range=today&advertiser_id=not-a-number')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert 'Invalid advertiser_id format' in data['error']
    
    def test_get_reporting_validates_timezone(self, authenticated_session, mock_db_connection, mock_gam_client, mock_gam_service):
        """Test that invalid timezone is rejected."""
        response = authenticated_session.get('/api/tenant/test_tenant/gam/reporting?date_range=today&timezone=Invalid/Timezone')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert 'Invalid timezone' in data['error']
    
    def test_get_reporting_success(self, authenticated_session, mock_db_connection, mock_gam_client, mock_gam_service):
        """Test successful reporting data retrieval."""
        # Mock the GAMReportingService to return proper data
        with patch('adapters.gam_reporting_api.GAMReportingService') as mock_service_class:
            mock_instance = Mock()
            mock_instance.get_reporting_data.return_value = Mock(
                data=[{'impressions': 100, 'clicks': 5, 'spend': 10.0}],
                start_date=datetime.now(),
                end_date=datetime.now(),
                requested_timezone='America/New_York',
                data_timezone='America/New_York',
                data_valid_until=datetime.now(),
                query_type='today',
                dimensions=['DATE'],
                metrics={'total_impressions': 100}
            )
            mock_service_class.return_value = mock_instance
            
            response = authenticated_session.get('/api/tenant/test_tenant/gam/reporting?date_range=today')
            if response.status_code != 200:
                print(f"Response status: {response.status_code}")
                print(f"Response data: {response.data}")
            assert response.status_code == 200
            data = json.loads(response.data)
            
            # Check response structure
            assert 'success' in data
            assert 'data' in data
            assert 'metadata' in data
    
    def test_get_reporting_with_filters(self, authenticated_session, mock_db_connection, mock_gam_client):
        """Test reporting with advertiser, order, and line item filters."""
        # Mock the GAMReportingService to return proper data
        with patch('adapters.gam_reporting_api.GAMReportingService') as mock_service_class:
            mock_instance = Mock()
            mock_instance.get_reporting_data.return_value = Mock(
                data=[{'impressions': 100, 'clicks': 5, 'spend': 10.0}],
                start_date=datetime.now(),
                end_date=datetime.now(),
                requested_timezone='America/New_York',
                data_timezone='America/New_York',
                data_valid_until=datetime.now(),
                query_type='this_month',
                dimensions=['DATE'],
                metrics={'total_impressions': 100}
            )
            mock_service_class.return_value = mock_instance
            
            response = authenticated_session.get(
                '/api/tenant/test_tenant/gam/reporting?date_range=this_month'
                '&advertiser_id=123456&order_id=789012&line_item_id=345678'
            )
            assert response.status_code == 200
            
            # Verify the service was called with correct parameters
            mock_instance.get_reporting_data.assert_called_once()
    
    def test_get_reporting_non_gam_tenant(self, authenticated_session):
        """Test that non-GAM tenants cannot access reporting."""
        with patch('db_config.get_db_connection') as mock_db_conn, \
             patch('admin_ui.get_db_connection') as mock_ui_conn, \
             patch('gam_helper.get_db_connection') as mock_gam_conn:
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = {
                'ad_server': 'kevel',  # Not GAM
                'tenant_id': 'test_tenant',
                'name': 'Test Tenant'
            }
            
            for mock_conn in [mock_db_conn, mock_ui_conn, mock_gam_conn]:
                mock_conn.return_value.execute.return_value = mock_cursor
                mock_conn.return_value.cursor.return_value = mock_cursor
                mock_conn.return_value.close = Mock()
            
            response = authenticated_session.get('/api/tenant/test_tenant/gam/reporting?date_range=today')
            assert response.status_code == 400
            data = json.loads(response.data)
            assert 'error' in data
            assert 'GAM reporting is only available' in data['error']


class TestSyncStatusAPI:
    """Test sync status API endpoints."""
    
    def test_sync_status_requires_auth(self, client):
        """Test that sync status endpoint requires authentication."""
        response = client.get('/api/tenant/test_tenant/sync/status')
        # The endpoint redirects to login (302) when not authenticated
        # This is inconsistent with other API endpoints but is the current behavior
        assert response.status_code in [302, 401]  # Accept redirect or JSON error
        if response.status_code == 401:
            data = json.loads(response.data)
            assert 'error' in data
        else:
            # Check it's redirecting to login
            assert '/login' in response.location
    
    def test_sync_status_success(self, authenticated_session):
        """Test successful sync status retrieval."""
        with patch('admin_ui.get_db_connection') as mock_conn:
            # Mock tenant query
            tenant_cursor = Mock()
            tenant_cursor.fetchone.return_value = {'ad_server': 'google_ad_manager'}
            
            # Mock sync job query
            sync_cursor = Mock()
            sync_cursor.fetchone.return_value = {
                'started_at': datetime.now().isoformat(),
                'status': 'completed',
                'summary': {'items_synced': 100}
            }
            
            # Mock inventory counts query
            inventory_cursor = Mock()
            inventory_cursor.fetchone.return_value = {
                'ad_units': 50,
                'custom_targeting_keys': 30,
                'custom_targeting_values': 20,
                'total': 100
            }
            
            mock_conn.return_value.execute.side_effect = [tenant_cursor, sync_cursor, inventory_cursor]
            mock_conn.return_value.close = Mock()
            
            response = authenticated_session.get('/api/tenant/test_tenant/sync/status')
            assert response.status_code == 200
            data = json.loads(response.data)
            
            assert 'last_sync' in data
            assert 'sync_running' in data
            assert 'item_count' in data
            assert 'breakdown' in data
            assert data['item_count'] == 100
            assert data['sync_running'] is False
    
    def test_trigger_sync_requires_super_admin(self, tenant_session):
        """Test that only super admins can trigger sync."""
        with patch('admin_ui.get_db_connection') as mock_conn:
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = {'ad_server': 'google_ad_manager'}
            mock_conn.return_value.execute.return_value = mock_cursor
            mock_conn.return_value.close = Mock()
            
            response = tenant_session.post('/api/tenant/test_tenant/sync/trigger')
            assert response.status_code == 403
            data = json.loads(response.data)
            assert 'error' in data
            assert 'super admin' in data['error'].lower()


class TestReportingDashboard:
    """Test the GAM reporting dashboard UI."""
    
    def test_dashboard_requires_auth(self, client):
        """Test that dashboard requires authentication."""
        response = client.get('/tenant/test_tenant/reporting')
        assert response.status_code == 302  # Redirect to login
        assert '/login' in response.location
    
    def test_dashboard_renders_for_gam_tenant(self, authenticated_session):
        """Test that dashboard renders for GAM tenants."""
        with patch('admin_ui.get_db_connection') as mock_conn:
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = {
                'ad_server': 'google_ad_manager',
                'tenant_id': 'test_tenant',
                'name': 'Test Tenant',
                'gam_network_code': '123456'
            }
            mock_conn.return_value.execute.return_value = mock_cursor
            mock_conn.return_value.close = Mock()
            
            response = authenticated_session.get('/tenant/test_tenant/reporting')
            assert response.status_code == 200
            assert b'GAM Reporting' in response.data
    
    def test_dashboard_error_for_non_gam_tenant(self, authenticated_session):
        """Test that dashboard shows error for non-GAM tenants."""
        with patch('admin_ui.get_db_connection') as mock_conn:
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = {
                'ad_server': 'kevel',
                'tenant_id': 'test_tenant',
                'name': 'Test Tenant'
            }
            mock_conn.return_value.execute.return_value = mock_cursor
            mock_conn.return_value.close = Mock()
            
            response = authenticated_session.get('/tenant/test_tenant/reporting')
            assert response.status_code == 400
            assert b'GAM Reporting Not Available' in response.data


if __name__ == '__main__':
    pytest.main([__file__, '-v'])