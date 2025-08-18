#!/usr/bin/env python3
"""
Test admin UI OAuth authentication flows.

This test suite covers:
1. Google OAuth login flow for super admins
2. Google OAuth login flow for tenant admins
3. Authentication decorators and session management
4. Authorization checks (super admin vs tenant admin)
5. Multi-tenant access scenarios
"""

import pytest
import json
import os
from unittest.mock import patch, MagicMock
from flask import session

pytestmark = pytest.mark.unit

# Mock database connections and OAuth before importing admin_ui
import sys
mock_db = MagicMock()
mock_cursor = MagicMock()
mock_cursor.fetchall.return_value = []
mock_db.execute.return_value = mock_cursor

with patch('db_config.get_db_connection', return_value=mock_db):
    with patch('admin_ui.get_db_connection', return_value=mock_db):
        # Mock gam_inventory_service to avoid database initialization
        sys.modules['gam_inventory_service'] = MagicMock()
        sys.modules['gam_inventory_service'].get_db_connection = MagicMock(return_value=mock_db)
        
        # Now import admin_ui
        from admin_ui import app, is_super_admin, is_tenant_admin, require_auth


@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key'
    
    # Override OAuth config for testing
    with patch('admin_ui.GOOGLE_CLIENT_ID', 'test-client-id'):
        with patch('admin_ui.GOOGLE_CLIENT_SECRET', 'test-client-secret'):
            with app.test_client() as client:
                yield client


@pytest.fixture
def mock_db():
    """Mock database connection."""
    with patch('admin_ui.get_db_connection') as mock:
        conn = MagicMock()
        mock.return_value = conn
        yield conn

@pytest.fixture
def mock_db_session():
    """Mock database session for ORM queries."""
    with patch('admin_ui.get_db_session') as mock:
        mock_session = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_session)
        mock_context.__exit__ = MagicMock(return_value=None)
        mock.return_value = mock_context
        yield mock_session


@pytest.fixture
def mock_google_oauth():
    """Mock Google OAuth object."""
    with patch('admin_ui.google') as mock:
        yield mock


class TestOAuthLogin:
    """Test OAuth login flows."""
    
    def test_login_page_renders(self, client):
        """Test that the login page renders correctly."""
        response = client.get('/login')
        assert response.status_code == 200
        assert b'Sign in' in response.data
    
    def test_tenant_login_page_renders(self, client, mock_db_session):
        """Test that the tenant-specific login page renders correctly."""
        # Mock tenant exists
        mock_tenant = MagicMock()
        mock_tenant.name = 'Test Tenant'
        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = mock_tenant
        mock_db_session.query.return_value = mock_query
        
        response = client.get('/tenant/test-tenant/login')
        assert response.status_code == 200
        assert b'Test Tenant' in response.data
    
    def test_tenant_login_page_404_for_invalid_tenant(self, client, mock_db_session):
        """Test that invalid tenant returns 404."""
        # Mock tenant doesn't exist
        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = None
        mock_db_session.query.return_value = mock_query
        
        response = client.get('/tenant/invalid-tenant/login')
        assert response.status_code == 404
    
    def test_google_auth_redirect(self, client, mock_google_oauth):
        """Test Google OAuth redirect for super admin."""
        mock_google_oauth.authorize_redirect.return_value = 'redirect-response'
        
        response = client.get('/auth/google')
        mock_google_oauth.authorize_redirect.assert_called_once()
    
    def test_tenant_google_auth_redirect(self, client, mock_google_oauth):
        """Test Google OAuth redirect for tenant-specific login."""
        mock_google_oauth.authorize_redirect.return_value = 'redirect-response'
        
        with client.session_transaction() as sess:
            # Session should store tenant_id
            response = client.get('/tenant/test-tenant/auth/google')
            
        mock_google_oauth.authorize_redirect.assert_called_once()
        
        # Check session stored tenant_id
        with client.session_transaction() as sess:
            assert sess.get('oauth_tenant_id') == 'test-tenant'


class TestOAuthCallback:
    """Test OAuth callback handling."""
    
    def test_google_callback_super_admin(self, client, mock_google_oauth):
        """Test successful Google OAuth callback for super admin."""
        # Mock token and user info
        mock_google_oauth.authorize_access_token.return_value = {
            'userinfo': {
                'email': 'admin@example.com',
                'name': 'Admin User'
            }
        }
        
        # Mock is_super_admin to return True
        with patch('admin_ui.is_super_admin', return_value=True):
            response = client.get('/auth/google/callback')
            
            # Should redirect to index
            assert response.status_code == 302
            assert response.location.endswith('/')
            
            # Check session
            with client.session_transaction() as sess:
                assert sess['authenticated'] is True
                assert sess['role'] == 'super_admin'
                assert sess['email'] == 'admin@example.com'
                assert sess['username'] == 'Admin User'
    
    def test_google_callback_tenant_admin_single_tenant(self, client, mock_google_oauth):
        """Test successful Google OAuth callback for tenant admin with single tenant access."""
        # Mock token and user info
        mock_google_oauth.authorize_access_token.return_value = {
            'userinfo': {
                'email': 'user@example.com',
                'name': 'Test User'
            }
        }
        
        # Mock is_tenant_admin to return single tenant
        with patch('admin_ui.is_super_admin', return_value=False):
            with patch('admin_ui.is_tenant_admin', return_value=[('tenant-1', 'Tenant One')]):
                response = client.get('/auth/google/callback')
                
                # Should redirect to tenant detail
                assert response.status_code == 302
                assert '/tenant/tenant-1' in response.location
                
                # Check session
                with client.session_transaction() as sess:
                    assert sess['authenticated'] is True
                    assert sess['role'] == 'tenant_admin'
                    assert sess['tenant_id'] == 'tenant-1'
                    assert sess['email'] == 'user@example.com'
    
    def test_google_callback_tenant_admin_multiple_tenants(self, client, mock_google_oauth):
        """Test Google OAuth callback for user with access to multiple tenants."""
        # Mock token and user info
        mock_google_oauth.authorize_access_token.return_value = {
            'userinfo': {
                'email': 'user@example.com',
                'name': 'Test User'
            }
        }
        
        # Mock is_tenant_admin to return multiple tenants
        tenants = [('tenant-1', 'Tenant One'), ('tenant-2', 'Tenant Two')]
        with patch('admin_ui.is_super_admin', return_value=False):
            with patch('admin_ui.is_tenant_admin', return_value=tenants):
                response = client.get('/auth/google/callback')
                
                # Should show tenant selection page
                assert response.status_code == 200
                assert b'Select Tenant' in response.data
                
                # Check session has pre-auth info
                with client.session_transaction() as sess:
                    assert sess.get('pre_auth_email') == 'user@example.com'
                    assert sess.get('available_tenants') == tenants
    
    def test_google_callback_unauthorized_user(self, client, mock_google_oauth):
        """Test Google OAuth callback for unauthorized user."""
        # Mock token and user info
        mock_google_oauth.authorize_access_token.return_value = {
            'userinfo': {
                'email': 'unauthorized@example.com',
                'name': 'Unauthorized User'
            }
        }
        
        # Mock both auth checks to return False
        with patch('admin_ui.is_super_admin', return_value=False):
            with patch('admin_ui.is_tenant_admin', return_value=False):
                response = client.get('/auth/google/callback')
                
                # Should show login page with error
                assert response.status_code == 200
                assert b'not authorized' in response.data
    
    def test_tenant_google_callback_with_user_in_db(self, client, mock_google_oauth, mock_db, mock_db_session):
        """Test tenant-specific OAuth callback for user in database."""
        # Set oauth_tenant_id in session (simulating tenant-specific login flow)
        with client.session_transaction() as sess:
            sess['oauth_tenant_id'] = 'test-tenant'
        
        # Mock token and user info
        mock_google_oauth.authorize_access_token.return_value = {
            'userinfo': {
                'email': 'dbuser@example.com',
                'name': 'DB User'
            }
        }
        
        # Create side_effect function for is_tenant_admin that returns different values
        # based on arguments
        def mock_is_tenant_admin_func(email, tenant_id=None):
            if tenant_id == 'test-tenant':
                return True  # When checking specific tenant, return boolean
            else:
                return [('test-tenant', 'Test Tenant')]  # When checking all tenants
        
        # Mock tenant lookup for database check
        cursor_tenant = MagicMock()
        cursor_tenant.fetchone.return_value = (
            json.dumps(['dbuser@example.com']),  # authorized_emails as JSON string
            json.dumps([])  # authorized_domains as JSON string
        )
        
        # Mock user lookup - return None to simulate user not in users table
        cursor_user = MagicMock()
        cursor_user.fetchone.return_value = None
        
        # Mock tenant name lookup
        cursor_name = MagicMock()
        cursor_name.fetchone.return_value = ('Test Tenant',)
        
        # Configure mock to return different cursors for different queries
        mock_db.execute.side_effect = [cursor_user, cursor_tenant, cursor_name]
        
        # Mock the ORM query for User
        mock_user = MagicMock()
        mock_user.is_active = True
        mock_user.last_login = None
        mock_user.google_id = None
        mock_user.role = 'admin'
        mock_user.user_id = 'user123'
        mock_user.name = 'DB User'
        
        # Mock tenant for the session
        mock_tenant = MagicMock()
        mock_tenant.name = 'Test Tenant'
        
        # Configure query to return user first, then tenant
        def query_side_effect(model):
            query_mock = MagicMock()
            if model.__name__ == 'User':
                query_mock.join.return_value.filter.return_value.first.return_value = mock_user
            else:  # Tenant
                query_mock.filter_by.return_value.first.return_value = mock_tenant
            return query_mock
            
        mock_db_session.query.side_effect = query_side_effect
        mock_db_session.commit = MagicMock()  # Mock the commit method
        
        # Mock is_tenant_admin with side_effect
        with patch('admin_ui.is_tenant_admin', side_effect=mock_is_tenant_admin_func):
            response = client.get('/auth/google/callback')
        
        # Should redirect to tenant detail
        assert response.status_code == 302
        assert '/tenant/test-tenant' in response.location
        
        # Check session
        with client.session_transaction() as sess:
            assert sess['authenticated'] is True
            assert sess['tenant_id'] == 'test-tenant'


class TestAuthorizationDecorators:
    """Test authorization decorators."""
    
    def test_require_auth_redirects_unauthenticated(self, client):
        """Test that @require_auth redirects unauthenticated users."""
        response = client.get('/')
        assert response.status_code == 302
        assert '/login' in response.location
    
    def test_require_auth_allows_authenticated(self, client):
        """Test that @require_auth allows authenticated users."""
        with client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['role'] = 'super_admin'
            sess['email'] = 'admin@example.com'
        
        # Mock database for the index route
        with patch('admin_ui.get_db_connection') as mock_conn:
            cursor = MagicMock()
            cursor.fetchall.return_value = []
            mock_conn.return_value.execute.return_value = cursor
            
            response = client.get('/')
            assert response.status_code == 200
    
    def test_require_auth_admin_only_blocks_tenant_admin(self, client):
        """Test that @require_auth(admin_only=True) blocks tenant admins."""
        with client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['role'] = 'tenant_admin'
            sess['tenant_id'] = 'test-tenant'
        
        response = client.get('/create_tenant')
        assert response.status_code == 403
        assert b'Super admin required' in response.data
    
    def test_require_auth_admin_only_allows_super_admin(self, client):
        """Test that @require_auth(admin_only=True) allows super admins."""
        with client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['role'] = 'super_admin'
            sess['email'] = 'admin@example.com'
        
        response = client.get('/create_tenant')
        # Should render the form (GET request)
        assert response.status_code == 200
        assert b'Create' in response.data or b'create' in response.data


class TestHelperFunctions:
    """Test helper functions."""
    
    def test_is_super_admin_email_list(self):
        """Test is_super_admin with email list."""
        with patch('admin_ui.SUPER_ADMIN_EMAILS', ['admin@example.com']):
            assert is_super_admin('admin@example.com') is True
            assert is_super_admin('user@example.com') is False
    
    def test_is_super_admin_domain_list(self):
        """Test is_super_admin with domain list."""
        with patch('admin_ui.SUPER_ADMIN_DOMAINS', ['example.com']):
            assert is_super_admin('anyone@example.com') is True
            assert is_super_admin('user@other.com') is False
    
    def test_is_tenant_admin_specific_tenant(self, mock_db, mock_db_session):
        """Test is_tenant_admin for specific tenant."""
        # Mock tenant with authorized emails and domains
        mock_tenant = MagicMock()
        mock_tenant.authorized_emails = ['user@example.com']
        mock_tenant.authorized_domains = ['allowed.com']
        
        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = mock_tenant
        mock_db_session.query.return_value = mock_query
        
        # Test authorized email
        assert is_tenant_admin('user@example.com', 'test-tenant') is True
        
        # Test authorized domain
        assert is_tenant_admin('anyone@allowed.com', 'test-tenant') is True
        
        # Test unauthorized
        assert is_tenant_admin('other@other.com', 'test-tenant') is False
    
    def test_is_tenant_admin_all_tenants(self, mock_db):
        """Test is_tenant_admin without specific tenant (returns list of authorized tenants)."""
        # Mock multiple tenants
        cursor = MagicMock()
        # Returns (tenant_id, name, authorized_emails, authorized_domains) for each tenant
        cursor.fetchall.return_value = [
            ('tenant-1', 'Tenant One', json.dumps(['user@example.com']), json.dumps([])),
            ('tenant-2', 'Tenant Two', json.dumps([]), json.dumps(['example.com'])),
            ('tenant-3', 'Tenant Three', json.dumps(['other@other.com']), json.dumps([]))
        ]
        mock_db.execute.return_value = cursor
        
        result = is_tenant_admin('user@example.com')
        assert isinstance(result, list)
        assert len(result) == 2  # Should have access to tenant-1 and tenant-2
        assert ('tenant-1', 'Tenant One') in result
        assert ('tenant-2', 'Tenant Two') in result
    
    def test_is_tenant_admin_inactive_tenant(self, mock_db):
        """Test is_tenant_admin ignores inactive tenants."""
        # Mock tenant that is not active
        cursor = MagicMock()
        cursor.fetchone.return_value = None  # No active tenant found
        mock_db.execute.return_value = cursor
        
        assert is_tenant_admin('user@example.com', 'inactive-tenant') is False
    
    def test_is_tenant_admin_json_parsing(self, mock_db):
        """Test is_tenant_admin handles both JSON strings and dicts."""
        # Test with string JSON
        cursor = MagicMock()
        cursor.fetchone.return_value = (
            '["user@example.com"]',  # authorized_emails as JSON string
            '[]'                      # authorized_domains as JSON string
        )
        mock_db.execute.return_value = cursor
        
        assert is_tenant_admin('user@example.com', 'test-tenant') is True
        
        # Test with empty strings
        cursor.fetchone.return_value = ('', '')
        assert is_tenant_admin('user@example.com', 'test-tenant') is False
        
        # Test with None values
        cursor.fetchone.return_value = (None, None)
        assert is_tenant_admin('user@example.com', 'test-tenant') is False


class TestSessionManagement:
    """Test session management."""
    
    def test_logout_clears_session(self, client):
        """Test that logout clears the session."""
        # Set up authenticated session
        with client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['role'] = 'super_admin'
            sess['email'] = 'admin@example.com'
        
        response = client.get('/logout')
        assert response.status_code == 302
        
        # Check session is cleared
        with client.session_transaction() as sess:
            assert 'authenticated' not in sess
            assert 'role' not in sess
            assert 'email' not in sess
    
    def test_logout_preserves_tenant_redirect(self, client):
        """Test that logout from tenant admin redirects to tenant login."""
        # Set up tenant admin session
        with client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['role'] = 'tenant_admin'
            sess['tenant_id'] = 'test-tenant'
            sess['email'] = 'user@example.com'
        
        response = client.get('/logout')
        assert response.status_code == 302
        assert '/tenant/test-tenant/login' in response.location
    
    def test_choose_tenant_sets_session(self, client):
        """Test choosing a tenant from multi-tenant selection."""
        # Set up pre-auth session
        with client.session_transaction() as sess:
            sess['pre_auth_email'] = 'user@example.com'
            sess['pre_auth_name'] = 'Test User'
            sess['available_tenants'] = [
                ('tenant-1', 'Tenant One'),
                ('tenant-2', 'Tenant Two')
            ]
        
        response = client.post('/auth/select-tenant', data={'tenant_id': 'tenant-1'})
        assert response.status_code == 302
        assert '/tenant/tenant-1' in response.location
        
        # Check session is properly set
        with client.session_transaction() as sess:
            assert sess['authenticated'] is True
            assert sess['role'] == 'tenant_admin'
            assert sess['tenant_id'] == 'tenant-1'
            assert sess['email'] == 'user@example.com'
            # Check cleanup of temporary session vars
            assert 'pre_auth_email' not in sess
            assert 'pre_auth_name' not in sess
            assert 'available_tenants' not in sess
    
    def test_choose_tenant_invalid_selection(self, client):
        """Test choosing an invalid tenant from selection."""
        # Set up pre-auth session
        with client.session_transaction() as sess:
            sess['pre_auth_email'] = 'user@example.com'
            sess['pre_auth_name'] = 'Test User'
            sess['available_tenants'] = [
                ('tenant-1', 'Tenant One'),
                ('tenant-2', 'Tenant Two')
            ]
        
        # Try to select a tenant not in the list
        response = client.post('/auth/select-tenant', data={'tenant_id': 'tenant-3'})
        assert response.status_code == 400
        assert b'Invalid tenant selection' in response.data
        
        # Session should not be authenticated
        with client.session_transaction() as sess:
            assert 'authenticated' not in sess
    
    def test_choose_tenant_without_pre_auth(self, client):
        """Test accessing choose_tenant without pre-auth redirects to login."""
        response = client.post('/auth/select-tenant', data={'tenant_id': 'tenant-1'})
        assert response.status_code == 302
        assert '/login' in response.location
    
    def test_oauth_tenant_id_cleanup(self, client, mock_google_oauth, mock_db):
        """Test that oauth_tenant_id is cleaned up after successful auth."""
        # Set oauth_tenant_id in session
        with client.session_transaction() as sess:
            sess['oauth_tenant_id'] = 'test-tenant'
        
        # Mock token and user info
        mock_google_oauth.authorize_access_token.return_value = {
            'userinfo': {
                'email': 'user@example.com',
                'name': 'Test User'
            }
        }
        
        # Create side_effect function for is_tenant_admin
        def mock_is_tenant_admin_func(email, tenant_id=None):
            if tenant_id == 'test-tenant':
                return True
            else:
                return [('test-tenant', 'Test Tenant')]
        
        # Mock user lookup - return None to simulate user not in users table
        cursor_user = MagicMock()
        cursor_user.fetchone.return_value = None
        
        # Mock tenant lookup
        cursor_tenant = MagicMock()
        cursor_tenant.fetchone.return_value = (
            json.dumps(['user@example.com']),  # authorized_emails
            json.dumps([])  # authorized_domains
        )
        
        # Mock tenant name lookup
        cursor_name = MagicMock()
        cursor_name.fetchone.return_value = ('Test Tenant',)
        
        # Configure mock to return different cursors for different queries
        mock_db.execute.side_effect = [cursor_user, cursor_tenant, cursor_name]
        
        # Mock is_tenant_admin
        with patch('admin_ui.is_tenant_admin', side_effect=mock_is_tenant_admin_func):
            # Process callback through unified endpoint
            response = client.get('/auth/google/callback')
            
            # Should redirect to tenant
            assert response.status_code == 302
            assert '/tenant/test-tenant' in response.location


class TestOAuthErrorHandling:
    """Test OAuth error handling scenarios."""
    
    def test_google_callback_no_token(self, client, mock_google_oauth):
        """Test Google OAuth callback when no token is returned."""
        # Mock authorize_access_token to raise exception
        mock_google_oauth.authorize_access_token.side_effect = Exception("OAuth error")
        
        response = client.get('/auth/google/callback')
        
        # Should show login page with error
        assert response.status_code == 200
        assert b'Authentication failed' in response.data
    
    def test_google_callback_no_userinfo(self, client, mock_google_oauth):
        """Test Google OAuth callback when userinfo is missing."""
        # Mock token without userinfo
        mock_google_oauth.authorize_access_token.return_value = {}
        
        response = client.get('/auth/google/callback')
        
        # Should redirect to login
        assert response.status_code == 302
        assert '/login' in response.location
    
    def test_google_callback_no_email(self, client, mock_google_oauth):
        """Test Google OAuth callback when email is missing from userinfo."""
        # Mock token with userinfo but no email
        mock_google_oauth.authorize_access_token.return_value = {
            'userinfo': {
                'name': 'Test User'
                # email is missing
            }
        }
        
        response = client.get('/auth/google/callback')
        
        # Should show login page with error
        assert response.status_code == 200
        assert b'No email address provided' in response.data
    
    def test_tenant_callback_inactive_user(self, client, mock_google_oauth, mock_db):
        """Test tenant OAuth callback for inactive tenant."""
        # Set oauth_tenant_id in session
        with client.session_transaction() as sess:
            sess['oauth_tenant_id'] = 'inactive-tenant'
        
        # Mock token and user info
        mock_google_oauth.authorize_access_token.return_value = {
            'userinfo': {
                'email': 'user@example.com',
                'name': 'Test User'
            }
        }
        
        # Create side_effect function for is_tenant_admin that returns empty list
        def mock_is_tenant_admin_func(email, tenant_id=None):
            if tenant_id == 'inactive-tenant':
                return False  # Tenant is inactive
            else:
                return []  # No tenants available
        
        # Mock user lookup - return None
        cursor_user = MagicMock()
        cursor_user.fetchone.return_value = None
        
        # Mock inactive tenant
        cursor_tenant = MagicMock()
        cursor_tenant.fetchone.return_value = None  # No active tenant found
        
        # Configure mock to return cursors
        mock_db.execute.side_effect = [cursor_user, cursor_tenant]
        
        # Mock is_tenant_admin to return empty list (no access)
        with patch('admin_ui.is_tenant_admin', side_effect=mock_is_tenant_admin_func):
            response = client.get('/auth/google/callback')
        
        # Should show login page with error
        assert response.status_code == 200
        assert b'not authorized' in response.data
    
    @patch('admin_ui.get_db_connection')
    def test_tenant_root_authenticated_redirect(self, mock_db, client):
        """Test tenant root shows dashboard for authenticated users."""
        # Mock database connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.execute.return_value = mock_cursor
        mock_db.return_value = mock_conn
        
        # Create a function that returns appropriate values
        def mock_fetchone():
            # Return tenant info first, then numeric values for everything else
            if not hasattr(mock_fetchone, 'call_count'):
                mock_fetchone.call_count = 0
            mock_fetchone.call_count += 1
            
            if mock_fetchone.call_count == 1:
                # Tenant query
                return ('test-tenant', 'Test Tenant', 'test', True, 'mock')
            else:
                # All metric queries return a numeric value
                return (0,)
        
        mock_cursor.fetchone.side_effect = mock_fetchone
        
        # Also need fetchall for some queries
        mock_cursor.fetchall.return_value = []
        
        # Set up authenticated session
        with client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['role'] = 'tenant_admin'
            sess['tenant_id'] = 'test-tenant'
        
        response = client.get('/tenant/test-tenant')
        # Dashboard should load successfully
        assert response.status_code == 200
    
    def test_cross_tenant_access_denied(self, client):
        """Test tenant admin cannot access another tenant's data."""
        # Set up tenant admin for tenant-1
        with client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['role'] = 'tenant_admin'
            sess['tenant_id'] = 'tenant-1'
            sess['email'] = 'admin@tenant1.com'
        
        # Mock database for tenant lookup
        with patch('admin_ui.get_db_connection') as mock_conn:
            cursor = MagicMock()
            cursor.fetchone.return_value = ('Tenant 2',)
            mock_conn.return_value.execute.return_value = cursor
            
            # Try to access tenant-2's dashboard
            response = client.get('/tenant/tenant-2')
            assert response.status_code == 403
            assert b'can only view your own tenant' in response.data
    
    def test_role_based_update_restrictions(self, client):
        """Test viewer role cannot update configuration."""
        # Set up viewer session
        with client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['role'] = 'viewer'
            sess['tenant_id'] = 'test-tenant'
            sess['email'] = 'viewer@example.com'
        
        # Try to update tenant
        response = client.post('/tenant/test-tenant/update', data={
            'name': 'Updated Name'
        })
        assert response.status_code == 403
        assert b'Viewers cannot update' in response.data


if __name__ == '__main__':
    pytest.main([__file__, '-v'])