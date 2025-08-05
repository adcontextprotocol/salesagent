"""Unit tests for the Super Admin API."""

import pytest
import json
import secrets
from unittest.mock import patch, MagicMock
from flask import Flask
from superadmin_api import superadmin_api
from models import Tenant, AdapterConfig, Principal, SuperadminConfig
from database import db_session
import logging

# Disable logging during tests
logging.disable(logging.CRITICAL)


@pytest.fixture
def app():
    """Create test Flask app."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(superadmin_api)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def api_key():
    """Generate test API key."""
    return f"sk-{secrets.token_urlsafe(32)}"


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    with patch('superadmin_api.db_session') as mock_session:
        yield mock_session


class TestSuperAdminAPI:
    """Test cases for Super Admin API endpoints."""
    
    def test_health_check_without_api_key(self, client):
        """Test health check fails without API key."""
        response = client.get('/api/v1/superadmin/health')
        assert response.status_code == 401
        assert response.json['error'] == 'Missing API key'
    
    def test_health_check_with_invalid_api_key(self, client, mock_db_session):
        """Test health check fails with invalid API key."""
        # Mock the API key query
        mock_config = MagicMock()
        mock_config.config_value = 'sk-valid-key'
        mock_db_session.query().filter_by().first.return_value = mock_config
        
        response = client.get('/api/v1/superadmin/health', 
                            headers={'X-Superadmin-API-Key': 'sk-invalid-key'})
        assert response.status_code == 401
        assert response.json['error'] == 'Invalid API key'
    
    def test_health_check_with_valid_api_key(self, client, mock_db_session, api_key):
        """Test health check succeeds with valid API key."""
        # Mock the API key query
        mock_config = MagicMock()
        mock_config.config_value = api_key
        mock_db_session.query().filter_by().first.return_value = mock_config
        
        response = client.get('/api/v1/superadmin/health', 
                            headers={'X-Superadmin-API-Key': api_key})
        assert response.status_code == 200
        assert response.json['status'] == 'healthy'
        assert 'timestamp' in response.json
    
    def test_list_tenants(self, client, mock_db_session, api_key):
        """Test listing tenants."""
        # Mock the API key query
        mock_config = MagicMock()
        mock_config.config_value = api_key
        
        # Mock tenants
        mock_tenant1 = MagicMock(spec=Tenant)
        mock_tenant1.tenant_id = 'tenant_123'
        mock_tenant1.name = 'Test Publisher'
        mock_tenant1.subdomain = 'test'
        mock_tenant1.is_active = True
        mock_tenant1.billing_plan = 'standard'
        mock_tenant1.ad_server = 'google_ad_manager'
        mock_tenant1.created_at.isoformat.return_value = '2025-01-06T12:00:00'
        
        mock_tenant2 = MagicMock(spec=Tenant)
        mock_tenant2.tenant_id = 'tenant_456'
        mock_tenant2.name = 'Another Publisher'
        mock_tenant2.subdomain = 'another'
        mock_tenant2.is_active = True
        mock_tenant2.billing_plan = 'premium'
        mock_tenant2.ad_server = 'kevel'
        mock_tenant2.created_at.isoformat.return_value = '2025-01-06T13:00:00'
        
        # Set up mock queries
        mock_db_session.query().filter_by().first.side_effect = [
            mock_config,  # First call for API key
            MagicMock(),  # Adapter config for tenant 1
            None          # Adapter config for tenant 2
        ]
        mock_db_session.query().all.return_value = [mock_tenant1, mock_tenant2]
        
        response = client.get('/api/v1/superadmin/tenants',
                            headers={'X-Superadmin-API-Key': api_key})
        
        assert response.status_code == 200
        data = response.json
        assert data['count'] == 2
        assert len(data['tenants']) == 2
        assert data['tenants'][0]['tenant_id'] == 'tenant_123'
        assert data['tenants'][0]['adapter_configured'] is True
        assert data['tenants'][1]['adapter_configured'] is False
    
    def test_create_tenant_missing_fields(self, client, mock_db_session, api_key):
        """Test creating tenant with missing required fields."""
        # Mock the API key query
        mock_config = MagicMock()
        mock_config.config_value = api_key
        mock_db_session.query().filter_by().first.return_value = mock_config
        
        response = client.post('/api/v1/superadmin/tenants',
                             headers={'X-Superadmin-API-Key': api_key},
                             json={'name': 'Test Publisher'})  # Missing subdomain and ad_server
        
        assert response.status_code == 400
        assert 'Missing required field' in response.json['error']
    
    def test_create_tenant_success(self, client, mock_db_session, api_key):
        """Test successful tenant creation."""
        # Mock the API key query
        mock_config = MagicMock()
        mock_config.config_value = api_key
        mock_db_session.query().filter_by().first.return_value = mock_config
        
        # Mock successful database operations
        mock_db_session.add.return_value = None
        mock_db_session.commit.return_value = None
        
        tenant_data = {
            'name': 'New Publisher',
            'subdomain': 'newpub',
            'ad_server': 'google_ad_manager',
            'gam_network_code': '123456789',
            'gam_refresh_token': 'test_refresh_token',
            'authorized_emails': ['admin@newpub.com']
        }
        
        response = client.post('/api/v1/superadmin/tenants',
                             headers={'X-Superadmin-API-Key': api_key},
                             json=tenant_data)
        
        assert response.status_code == 201
        data = response.json
        assert 'tenant_id' in data
        assert data['name'] == 'New Publisher'
        assert data['subdomain'] == 'newpub'
        assert 'admin_token' in data
        assert 'admin_ui_url' in data
        assert 'default_principal_token' in data  # Because create_default_principal defaults to True
    
    def test_get_tenant_not_found(self, client, mock_db_session, api_key):
        """Test getting non-existent tenant."""
        # Mock the API key query
        mock_config = MagicMock()
        mock_config.config_value = api_key
        mock_db_session.query().filter_by().first.side_effect = [
            mock_config,  # API key query
            None         # Tenant query
        ]
        
        response = client.get('/api/v1/superadmin/tenants/nonexistent',
                            headers={'X-Superadmin-API-Key': api_key})
        
        assert response.status_code == 404
        assert response.json['error'] == 'Tenant not found'
    
    def test_update_tenant(self, client, mock_db_session, api_key):
        """Test updating a tenant."""
        # Mock the API key query
        mock_config = MagicMock()
        mock_config.config_value = api_key
        
        # Mock tenant
        mock_tenant = MagicMock(spec=Tenant)
        mock_tenant.tenant_id = 'tenant_123'
        mock_tenant.name = 'Old Name'
        mock_tenant.billing_plan = 'standard'
        mock_tenant.updated_at.isoformat.return_value = '2025-01-06T14:00:00'
        
        # Mock adapter config
        mock_adapter = MagicMock(spec=AdapterConfig)
        mock_adapter.adapter_type = 'google_ad_manager'
        
        mock_db_session.query().filter_by().first.side_effect = [
            mock_config,    # API key query
            mock_tenant,    # Tenant query
            mock_adapter    # Adapter config query
        ]
        mock_db_session.commit.return_value = None
        
        update_data = {
            'name': 'New Name',
            'billing_plan': 'premium',
            'adapter_config': {
                'gam_company_id': 'new_company_123'
            }
        }
        
        response = client.put('/api/v1/superadmin/tenants/tenant_123',
                            headers={'X-Superadmin-API-Key': api_key},
                            json=update_data)
        
        assert response.status_code == 200
        assert mock_tenant.name == 'New Name'
        assert mock_tenant.billing_plan == 'premium'
        assert mock_adapter.gam_company_id == 'new_company_123'
    
    def test_delete_tenant_soft(self, client, mock_db_session, api_key):
        """Test soft deleting a tenant."""
        # Mock the API key query
        mock_config = MagicMock()
        mock_config.config_value = api_key
        
        # Mock tenant
        mock_tenant = MagicMock(spec=Tenant)
        mock_tenant.tenant_id = 'tenant_123'
        mock_tenant.is_active = True
        
        mock_db_session.query().filter_by().first.side_effect = [
            mock_config,  # API key query
            mock_tenant   # Tenant query
        ]
        mock_db_session.commit.return_value = None
        
        response = client.delete('/api/v1/superadmin/tenants/tenant_123',
                               headers={'X-Superadmin-API-Key': api_key})
        
        assert response.status_code == 200
        assert mock_tenant.is_active is False
        assert 'deactivated' in response.json['message']
    
    def test_delete_tenant_hard(self, client, mock_db_session, api_key):
        """Test hard deleting a tenant."""
        # Mock the API key query
        mock_config = MagicMock()
        mock_config.config_value = api_key
        
        # Mock tenant
        mock_tenant = MagicMock(spec=Tenant)
        mock_tenant.tenant_id = 'tenant_123'
        
        mock_db_session.query().filter_by().first.side_effect = [
            mock_config,  # API key query
            mock_tenant   # Tenant query
        ]
        mock_db_session.delete.return_value = None
        mock_db_session.commit.return_value = None
        
        response = client.delete('/api/v1/superadmin/tenants/tenant_123?hard_delete=true',
                               headers={'X-Superadmin-API-Key': api_key})
        
        assert response.status_code == 200
        assert 'permanently deleted' in response.json['message']
        mock_db_session.delete.assert_called_once_with(mock_tenant)
    
    def test_init_api_key_success(self, client, mock_db_session):
        """Test initializing API key for the first time."""
        # Mock no existing API key
        mock_db_session.query().filter_by().first.return_value = None
        mock_db_session.add.return_value = None
        mock_db_session.commit.return_value = None
        
        response = client.post('/api/v1/superadmin/init-api-key')
        
        assert response.status_code == 201
        data = response.json
        assert 'api_key' in data
        assert data['api_key'].startswith('sk-')
        assert 'warning' in data
    
    def test_init_api_key_already_exists(self, client, mock_db_session):
        """Test initializing API key when it already exists."""
        # Mock existing API key
        mock_config = MagicMock()
        mock_db_session.query().filter_by().first.return_value = mock_config
        
        response = client.post('/api/v1/superadmin/init-api-key')
        
        assert response.status_code == 409
        assert response.json['error'] == 'API key already initialized'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])