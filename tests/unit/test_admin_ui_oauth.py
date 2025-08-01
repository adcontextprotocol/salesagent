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
    
    def test_tenant_login_page_renders(self, client, mock_db):
        """Test that the tenant-specific login page renders correctly."""
        # Mock tenant exists
        cursor = MagicMock()
        cursor.fetchone.return_value = ('Test Tenant',)
        mock_db.execute.return_value = cursor
        
        response = client.get('/tenant/test-tenant/login')
        assert response.status_code == 200
        assert b'Test Tenant' in response.data
    
    def test_tenant_login_page_404_for_invalid_tenant(self, client, mock_db):
        """Test that invalid tenant returns 404."""
        # Mock tenant doesn't exist
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        mock_db.execute.return_value = cursor
        
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
    
    def test_tenant_google_callback_with_user_in_db(self, client, mock_google_oauth, mock_db):
        """Test tenant-specific OAuth callback for user in database."""
        # Mock token and user info
        mock_google_oauth.authorize_access_token.return_value = {
            'userinfo': {
                'email': 'dbuser@example.com',
                'name': 'DB User'
            }
        }
        
        # Mock user exists in database
        cursor = MagicMock()
        cursor.fetchone.return_value = (
            'user-123',  # user_id
            'tenant_admin',  # role
            'DB User',  # name
            'Test Tenant',  # tenant_name
            True  # is_active
        )
        mock_db.execute.return_value = cursor
        
        response = client.get('/tenant/test-tenant/auth/google/callback')
        
        # Should redirect to tenant detail
        assert response.status_code == 302
        assert '/tenant/test-tenant' in response.location
        
        # Check session
        with client.session_transaction() as sess:
            assert sess['authenticated'] is True
            assert sess['role'] == 'tenant_admin'
            assert sess['user_id'] == 'user-123'


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
    
    def test_is_tenant_admin_specific_tenant(self, mock_db):
        """Test is_tenant_admin for specific tenant."""
        # Mock tenant config with authorized emails
        cursor = MagicMock()
        cursor.fetchone.return_value = (json.dumps({
            'authorized_emails': ['user@example.com'],
            'authorized_domains': ['allowed.com']
        }),)
        mock_db.execute.return_value = cursor
        
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
        cursor.fetchall.return_value = [
            ('tenant-1', 'Tenant One', json.dumps({'authorized_emails': ['user@example.com']})),
            ('tenant-2', 'Tenant Two', json.dumps({'authorized_domains': ['example.com']})),
            ('tenant-3', 'Tenant Three', json.dumps({'authorized_emails': ['other@other.com']}))
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
        cursor.fetchone.return_value = ('{"authorized_emails": ["user@example.com"]}',)
        mock_db.execute.return_value = cursor
        
        assert is_tenant_admin('user@example.com', 'test-tenant') is True
        
        # Test with dict (already parsed)
        cursor.fetchone.return_value = ({'authorized_emails': ['user@example.com']},)
        assert is_tenant_admin('user@example.com', 'test-tenant') is True


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
        # Mock token and user info
        mock_google_oauth.authorize_access_token.return_value = {
            'userinfo': {
                'email': 'user@example.com',
                'name': 'Test User'
            }
        }
        
        # Mock user in database
        cursor = MagicMock()
        cursor.fetchone.return_value = (
            'user-123', 'tenant_admin', 'Test User', 'Test Tenant', True
        )
        mock_db.execute.return_value = cursor
        
        # Set oauth_tenant_id in session
        with client.session_transaction() as sess:
            sess['oauth_tenant_id'] = 'test-tenant'
        
        response = client.get('/tenant/test-tenant/auth/google/callback')
        
        # Check oauth_tenant_id is cleaned up
        with client.session_transaction() as sess:
            assert 'oauth_tenant_id' not in sess


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
        """Test tenant OAuth callback for inactive user in database."""
        # Mock token and user info
        mock_google_oauth.authorize_access_token.return_value = {
            'userinfo': {
                'email': 'inactive@example.com',
                'name': 'Inactive User'
            }
        }
        
        # Mock inactive user in database
        cursor = MagicMock()
        cursor.fetchone.return_value = (
            'user-123',  # user_id
            'tenant_admin',  # role
            'Inactive User',  # name
            'Test Tenant',  # tenant_name
            False  # is_active = False
        )
        mock_db.execute.return_value = cursor
        
        response = client.get('/tenant/test-tenant/auth/google/callback')
        
        # Should show error for inactive user
        assert response.status_code == 200
        assert b'disabled' in response.data or b'inactive' in response.data
    
    def test_tenant_root_authenticated_redirect(self, client):
        """Test tenant root redirects authenticated users to manage page."""
        # Set up authenticated session
        with client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['role'] = 'tenant_admin'
            sess['tenant_id'] = 'test-tenant'
        
        response = client.get('/tenant/test-tenant')
        assert response.status_code == 302
        assert '/tenant/test-tenant/manage' in response.location
    
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
            
            # Try to access tenant-2
            response = client.get('/tenant/tenant-2/manage')
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