"""
Unit tests for the Super Admin API endpoints.
"""

import json
import pytest
import secrets
import logging
from unittest.mock import MagicMock, patch, Mock
from flask import Flask
from superadmin_api import superadmin_api

pytestmark = pytest.mark.unit

# Disable logging during tests
logging.disable(logging.CRITICAL)


@pytest.fixture
def app():
    """Create test Flask app."""
    app = Flask(__name__)
    app.config["TESTING"] = True
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
def mock_session():
    """Mock database session."""
    with patch("superadmin_api.get_db_session") as mock_get_session:
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)
        mock_get_session.return_value = mock_session
        yield mock_session


class TestSuperAdminHealthAPI:
    """Test health check endpoints."""

    def test_health_check_with_invalid_api_key(self, client, mock_session):
        """Test health check fails with invalid API key."""
        # Mock returns None for invalid key
        mock_session.query.return_value.filter_by.return_value.first.return_value = None
        
        response = client.get("/api/v1/superadmin/health", 
                            headers={"X-Superadmin-API-Key": "sk-invalid-key"})
        assert response.status_code == 401
        assert response.json["error"] == "Invalid API key"

    def test_health_check_with_valid_api_key(self, client, mock_session, api_key):
        """Test health check succeeds with valid API key."""
        # Mock the API key config
        mock_config = MagicMock()
        mock_config.config_value = api_key
        mock_session.query.return_value.filter_by.return_value.first.return_value = mock_config

        response = client.get("/api/v1/superadmin/health", 
                            headers={"X-Superadmin-API-Key": api_key})
        assert response.status_code == 200
        assert response.json["status"] == "healthy"
        assert "timestamp" in response.json


class TestSuperAdminTenantAPI:
    """Test tenant management endpoints."""

    def test_list_tenants(self, client, mock_session, api_key):
        """Test listing tenants."""
        # Set up separate query chains
        auth_query_chain = MagicMock()
        mock_config = MagicMock()
        mock_config.config_value = api_key
        auth_query_chain.filter_by.return_value.first.return_value = mock_config
        
        # Mock tenants
        mock_tenant1 = MagicMock()
        mock_tenant1.tenant_id = "tenant_123"
        mock_tenant1.name = "Test Publisher"
        mock_tenant1.subdomain = "test"
        mock_tenant1.is_active = True
        mock_tenant1.billing_plan = "standard"
        mock_tenant1.created_at = "2025-01-06T12:00:00"
        mock_tenant1.policy_enabled = True
        
        mock_adapter1 = MagicMock()
        mock_adapter1.ad_server = "google_ad_manager"
        
        mock_tenant2 = MagicMock()
        mock_tenant2.tenant_id = "tenant_456"
        mock_tenant2.name = "Another Publisher"
        mock_tenant2.subdomain = "another"
        mock_tenant2.is_active = True
        mock_tenant2.billing_plan = "premium"
        mock_tenant2.created_at = "2025-01-07T12:00:00"
        mock_tenant2.policy_enabled = False
        
        mock_adapter2 = MagicMock()
        mock_adapter2.ad_server = "mock"
        
        tenant_query_chain = MagicMock()
        tenant_query_chain.outerjoin.return_value.all.return_value = [
            (mock_tenant1, mock_adapter1),
            (mock_tenant2, mock_adapter2)
        ]
        
        # Configure query() to return different chains based on call count
        mock_session.query.side_effect = [auth_query_chain, tenant_query_chain]

        response = client.get("/api/v1/superadmin/tenants", 
                            headers={"X-Superadmin-API-Key": api_key})

        assert response.status_code == 200
        data = response.json
        assert len(data["tenants"]) == 2
        assert data["tenants"][0]["tenant_id"] == "tenant_123"
        assert data["tenants"][0]["name"] == "Test Publisher"
        assert data["tenants"][1]["tenant_id"] == "tenant_456"
        assert data["count"] == 2

    def test_create_tenant_missing_fields(self, client, mock_session, api_key):
        """Test creating tenant with missing required fields."""
        # Mock the API key config
        mock_config = MagicMock()
        mock_config.config_value = api_key
        mock_session.query.return_value.filter_by.return_value.first.return_value = mock_config

        response = client.post(
            "/api/v1/superadmin/tenants", 
            headers={"X-Superadmin-API-Key": api_key}, 
            json={"name": "Test"}
        )

        assert response.status_code == 400
        assert "Missing required field" in response.json["error"]

    def test_create_tenant_success(self, client, mock_session, api_key):
        """Test successful tenant creation."""
        # Set up auth query
        auth_query = MagicMock()
        mock_config = MagicMock()
        mock_config.config_value = api_key
        auth_query.filter_by.return_value.first.return_value = mock_config
        
        # Set up duplicate check queries (both return None - no duplicates)
        duplicate_query1 = MagicMock()
        duplicate_query1.filter_by.return_value.first.return_value = None
        
        duplicate_query2 = MagicMock()
        duplicate_query2.filter_by.return_value.first.return_value = None
        
        # Configure query() to return different chains
        mock_session.query.side_effect = [auth_query, duplicate_query1, duplicate_query2]
        
        # Mock add and commit
        mock_session.add = MagicMock()
        mock_session.commit = MagicMock()

        payload = {
            "name": "New Publisher",
            "subdomain": "new",
            "billing_plan": "standard",
            "ad_server": "google_ad_manager",
            "network_code": "123456",
            "refresh_token": "test_token",
        }

        response = client.post("/api/v1/superadmin/tenants", 
                             headers={"X-Superadmin-API-Key": api_key}, 
                             json=payload)

        assert response.status_code == 201
        assert "tenant_id" in response.json
        assert "admin_token" in response.json
        assert response.json["subdomain"] == "new"

    def test_get_tenant_not_found(self, client, mock_session, api_key):
        """Test getting non-existent tenant."""
        # Mock auth
        auth_query = MagicMock()
        mock_config = MagicMock()
        mock_config.config_value = api_key
        auth_query.filter_by.return_value.first.return_value = mock_config
        
        # Mock tenant query - not found
        tenant_query = MagicMock()
        tenant_query.filter_by.return_value.first.return_value = None
        
        mock_session.query.side_effect = [auth_query, tenant_query]

        response = client.get("/api/v1/superadmin/tenants/nonexistent", 
                            headers={"X-Superadmin-API-Key": api_key})

        assert response.status_code == 404
        assert response.json["error"] == "Tenant not found"

    def test_update_tenant(self, client, mock_session, api_key):
        """Test updating tenant configuration."""
        # Mock auth
        auth_query = MagicMock()
        mock_config = MagicMock()
        mock_config.config_value = api_key
        auth_query.filter_by.return_value.first.return_value = mock_config
        
        # Mock tenant lookup
        tenant_query = MagicMock()
        mock_tenant = MagicMock()
        mock_tenant.tenant_id = "tenant_123"
        mock_tenant.name = "Test Publisher"
        mock_tenant.subdomain = "test"
        mock_tenant.is_active = True
        mock_tenant.billing_plan = "standard"
        mock_tenant.updated_at = "2025-01-06T13:00:00"
        tenant_query.filter_by.return_value.first.return_value = mock_tenant
        
        mock_session.query.side_effect = [auth_query, tenant_query]
        mock_session.commit = MagicMock()

        payload = {"name": "Updated Publisher", "billing_plan": "premium"}

        response = client.put(
            "/api/v1/superadmin/tenants/tenant_123", 
            headers={"X-Superadmin-API-Key": api_key}, 
            json=payload
        )

        assert response.status_code == 200
        assert response.json["tenant_id"] == "tenant_123"
        assert "updated_at" in response.json

    def test_delete_tenant_soft(self, client, mock_session, api_key):
        """Test soft deleting a tenant."""
        # Mock auth
        auth_query = MagicMock()
        mock_config = MagicMock()
        mock_config.config_value = api_key
        auth_query.filter_by.return_value.first.return_value = mock_config
        
        # Mock tenant lookup
        tenant_query = MagicMock()
        mock_tenant = MagicMock()
        mock_tenant.tenant_id = "tenant_123"
        mock_tenant.name = "Test Publisher"
        mock_tenant.is_active = True
        tenant_query.filter_by.return_value.first.return_value = mock_tenant
        
        mock_session.query.side_effect = [auth_query, tenant_query]
        mock_session.commit = MagicMock()

        response = client.delete(
            "/api/v1/superadmin/tenants/tenant_123", 
            headers={"X-Superadmin-API-Key": api_key}, 
            json={"hard_delete": False}
        )

        assert response.status_code == 200
        assert response.json["message"] == "Tenant soft deleted successfully"
        # Verify is_active was set to False
        assert mock_tenant.is_active == False

    def test_delete_tenant_hard(self, client, mock_session, api_key):
        """Test hard deleting a tenant."""
        # Mock auth
        auth_query = MagicMock()
        mock_config = MagicMock()
        mock_config.config_value = api_key
        auth_query.filter_by.return_value.first.return_value = mock_config
        
        # Mock tenant lookup
        tenant_query = MagicMock()
        mock_tenant = MagicMock()
        mock_tenant.tenant_id = "tenant_123"
        tenant_query.filter_by.return_value.first.return_value = mock_tenant
        
        # Mock related data queries for cascade delete
        for _ in range(8):  # Number of related tables
            related_query = MagicMock()
            related_query.filter_by.return_value.delete.return_value = None
            mock_session.query.side_effect = [related_query]
        
        # Reset side_effect for main queries
        mock_session.query.side_effect = [auth_query, tenant_query]
        
        # Mock the filter_by().delete() chain for related tables
        delete_chain = MagicMock()
        delete_chain.delete.return_value = 0
        mock_session.query.return_value.filter_by.return_value = delete_chain
        
        mock_session.delete = MagicMock()
        mock_session.commit = MagicMock()

        response = client.delete(
            "/api/v1/superadmin/tenants/tenant_123", 
            headers={"X-Superadmin-API-Key": api_key}, 
            json={"hard_delete": True}
        )

        assert response.status_code == 200
        assert response.json["message"] == "Tenant and all related data permanently deleted"

    def test_init_api_key_success(self, client, mock_session):
        """Test initializing API key."""
        # Mock no existing key
        mock_session.query.return_value.filter_by.return_value.first.return_value = None
        mock_session.add = MagicMock()
        mock_session.commit = MagicMock()

        response = client.post("/api/v1/superadmin/init-api-key")

        assert response.status_code == 200
        assert "api_key" in response.json
        assert response.json["api_key"].startswith("sk-")

    def test_init_api_key_already_exists(self, client, mock_session):
        """Test initializing API key when it already exists."""
        # Mock existing key
        mock_config = MagicMock()
        mock_config.config_value = "existing-key"
        mock_session.query.return_value.filter_by.return_value.first.return_value = mock_config

        response = client.post("/api/v1/superadmin/init-api-key")

        assert response.status_code == 400
        assert response.json["error"] == "API key already initialized"