"""Unit tests for the Super Admin API."""

import logging
import secrets
from unittest.mock import MagicMock, patch

import pytest
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
    """Mock database connection."""
    with patch("superadmin_api.get_db_session") as mock_conn:
        # Mock the database session
        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = None
        mock_session.query.return_value.filter_by.return_value.all.return_value = []
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_session.query.return_value.filter.return_value.all.return_value = []
        mock_session.query.return_value.all.return_value = []
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_conn.return_value = mock_session
        yield mock_session


class TestSuperAdminHealthAPI:
    """Test health check endpoints."""

    def test_health_check_with_invalid_api_key(self, client):
        """Test health check fails with invalid API key."""
        response = client.get("/api/v1/superadmin/health", headers={"X-Superadmin-API-Key": "sk-invalid-key"})
        assert response.status_code == 401
        assert response.json["error"] == "Invalid API key"

    def test_health_check_with_valid_api_key(self, client, mock_session, api_key):
        """Test health check succeeds with valid API key."""
        # Mock the API key query - returns just the config_value
        mock_query = MagicMock()
        mock_query.fetchone.return_value = (api_key,)  # Just config_value as a tuple
        mock_session.execute.return_value = mock_query

        response = client.get("/api/v1/superadmin/health", headers={"X-Superadmin-API-Key": api_key})
        assert response.status_code == 200
        assert response.json["status"] == "healthy"
        assert "timestamp" in response.json


class TestSuperAdminTenantAPI:
    """Test tenant management endpoints."""

    def test_list_tenants(self, client, mock_session, api_key):
        """Test listing tenants."""
        # Mock the API key query
        mock_cursor_auth = MagicMock()
        mock_cursor_auth.fetchone.return_value = (api_key,)  # Just config_value

        # Mock tenants query
        mock_cursor_tenants = MagicMock()
        mock_cursor_tenants.fetchall.return_value = [
            ("tenant_123", "Test Publisher", "test", 1, "standard", "google_ad_manager", "2025-01-06T12:00:00", 1),
            ("tenant_456", "Another Publisher", "another", 1, "premium", "mock", "2025-01-07T12:00:00", 0),
        ]

        # Configure mock to return different cursors for different queries
        mock_session.execute.side_effect = [mock_cursor_auth, mock_cursor_tenants]

        response = client.get("/api/v1/superadmin/tenants", headers={"X-Superadmin-API-Key": api_key})

        assert response.status_code == 200
        data = response.json
        assert len(data["tenants"]) == 2
        assert data["tenants"][0]["tenant_id"] == "tenant_123"
        assert data["tenants"][0]["name"] == "Test Publisher"
        assert data["tenants"][1]["tenant_id"] == "tenant_456"
        assert data["count"] == 2

    def test_create_tenant_missing_fields(self, client, mock_session, api_key):
        """Test creating tenant with missing required fields."""
        # Mock the API key query
        mock_query = MagicMock()
        mock_query.fetchone.return_value = (api_key,)  # Just config_value
        mock_session.execute.return_value = mock_query

        response = client.post(
            "/api/v1/superadmin/tenants", headers={"X-Superadmin-API-Key": api_key}, json={"name": "Test"}
        )

        assert response.status_code == 400
        assert "Missing required field" in response.json["error"]

    def test_create_tenant_success(self, client, mock_session, api_key):
        """Test successful tenant creation."""
        # Mock the API key query
        mock_cursor_auth = MagicMock()
        mock_cursor_auth.fetchone.return_value = (api_key,)  # Just config_value

        # Mock tenant exists check
        mock_cursor_check = MagicMock()
        mock_cursor_check.fetchone.return_value = None  # No existing tenant

        # Mock INSERT operations (returns cursor for all INSERTs)
        mock_cursor_insert = MagicMock()

        # Configure mock to return different cursors for different queries
        mock_session.execute.side_effect = [
            mock_cursor_auth,  # Auth check
            mock_cursor_check,  # Subdomain exists check
            mock_cursor_insert,  # INSERT INTO tenants
            mock_cursor_insert,  # INSERT INTO adapter_config
        ]
        mock_session.connection = MagicMock()
        mock_session.connection.commit = MagicMock()

        payload = {
            "name": "New Publisher",
            "subdomain": "new",
            "billing_plan": "standard",
            "ad_server": "google_ad_manager",
            "network_code": "123456",
            "refresh_token": "test_token",
        }

        response = client.post("/api/v1/superadmin/tenants", headers={"X-Superadmin-API-Key": api_key}, json=payload)

        assert response.status_code == 201
        assert "tenant_id" in response.json
        assert "admin_token" in response.json
        assert response.json["subdomain"] == "new"

    def test_get_tenant_not_found(self, client, mock_session, api_key):
        """Test getting non-existent tenant."""
        # Mock the API key query
        mock_cursor_auth = MagicMock()
        mock_cursor_auth.fetchone.return_value = (api_key,)

        # Mock tenant query - not found
        mock_cursor_tenant = MagicMock()
        mock_cursor_tenant.fetchone.return_value = None

        mock_session.execute.side_effect = [mock_cursor_auth, mock_cursor_tenant]

        response = client.get("/api/v1/superadmin/tenants/nonexistent", headers={"X-Superadmin-API-Key": api_key})

        assert response.status_code == 404
        assert response.json["error"] == "Tenant not found"

    def test_update_tenant(self, client, mock_session, api_key):
        """Test updating tenant configuration."""
        # Mock the API key query
        mock_cursor_auth = MagicMock()
        mock_cursor_auth.fetchone.return_value = (api_key,)

        # Mock tenant exists check
        mock_cursor_check = MagicMock()
        mock_cursor_check.fetchone.return_value = (
            "tenant_123",
            "Test Publisher",
            "test",
            1,
            "standard",
            "google_ad_manager",
            "2025-01-06T12:00:00",
        )

        # Mock UPDATE operation
        mock_cursor_update = MagicMock()

        # Mock final SELECT for response
        mock_cursor_select = MagicMock()
        mock_cursor_select.fetchone.return_value = ("Updated Publisher", "2025-01-06T13:00:00")

        mock_session.execute.side_effect = [mock_cursor_auth, mock_cursor_check, mock_cursor_update, mock_cursor_select]
        mock_session.connection = MagicMock()
        mock_session.connection.commit = MagicMock()

        payload = {"name": "Updated Publisher", "billing_plan": "premium"}

        response = client.put(
            "/api/v1/superadmin/tenants/tenant_123", headers={"X-Superadmin-API-Key": api_key}, json=payload
        )

        assert response.status_code == 200
        assert response.json["tenant_id"] == "tenant_123"
        assert "updated_at" in response.json

    def test_delete_tenant_soft(self, client, mock_session, api_key):
        """Test soft deleting a tenant."""
        # Mock the API key query
        mock_cursor_auth = MagicMock()
        mock_cursor_auth.fetchone.return_value = (api_key,)

        # Mock tenant exists check
        mock_cursor_check = MagicMock()
        mock_cursor_check.fetchone.return_value = (
            "tenant_123",
            "Test Publisher",
            "test",
            1,
            "standard",
            "google_ad_manager",
            "2025-01-06T12:00:00",
        )

        # Mock UPDATE operation for soft delete
        mock_cursor_update = MagicMock()

        mock_session.execute.side_effect = [mock_cursor_auth, mock_cursor_check, mock_cursor_update]
        mock_session.connection = MagicMock()
        mock_session.connection.commit = MagicMock()

        response = client.delete("/api/v1/superadmin/tenants/tenant_123", headers={"X-Superadmin-API-Key": api_key})

        assert response.status_code == 200
        assert response.json["message"] == "Tenant tenant_123 deactivated"
        mock_session.connection.commit.assert_called()

    def test_delete_tenant_hard(self, client, mock_session, api_key):
        """Test hard deleting a tenant."""
        # Mock the API key query
        mock_cursor_auth = MagicMock()
        mock_cursor_auth.fetchone.return_value = (api_key,)

        # Mock tenant exists check
        mock_cursor_check = MagicMock()
        mock_cursor_check.fetchone.return_value = (
            "tenant_123",
            "Test Publisher",
            "test",
            1,
            "standard",
            "google_ad_manager",
            "2025-01-06T12:00:00",
        )

        # Mock DELETE operations
        mock_cursor_delete = MagicMock()

        # Need multiple deletes for hard delete (from different tables)
        mock_session.execute.side_effect = [
            mock_cursor_auth,  # Auth check
            mock_cursor_check,  # Tenant exists check
            mock_cursor_delete,  # DELETE FROM adapter_config
            mock_cursor_delete,  # DELETE FROM principals
            mock_cursor_delete,  # DELETE FROM products
            mock_cursor_delete,  # DELETE FROM media_buys
            mock_cursor_delete,  # DELETE FROM creatives
            mock_cursor_delete,  # DELETE FROM creative_associations
            mock_cursor_delete,  # DELETE FROM human_tasks
            mock_cursor_delete,  # DELETE FROM tasks
            mock_cursor_delete,  # DELETE FROM audit_logs
            mock_cursor_delete,  # DELETE FROM users
            mock_cursor_delete,  # DELETE FROM tenants
        ]
        mock_session.connection = MagicMock()
        mock_session.connection.commit = MagicMock()

        response = client.delete(
            "/api/v1/superadmin/tenants/tenant_123?hard_delete=true", headers={"X-Superadmin-API-Key": api_key}
        )

        assert response.status_code == 200
        assert response.json["message"] == "Tenant tenant_123 permanently deleted"
        mock_session.connection.commit.assert_called()

    def test_init_api_key_success(self, client, mock_session):
        """Test initializing API key for the first time."""
        # Mock no existing API key (first check)
        mock_cursor_check = MagicMock()
        mock_cursor_check.fetchone.return_value = None

        # Mock INSERT operation
        mock_cursor_insert = MagicMock()

        mock_session.execute.side_effect = [mock_cursor_check, mock_cursor_insert]
        mock_session.connection = MagicMock()
        mock_session.connection.commit = MagicMock()

        response = client.post("/api/v1/superadmin/init-api-key")

        assert response.status_code == 201
        assert "api_key" in response.json
        assert response.json["api_key"].startswith("sk-")
        mock_session.connection.commit.assert_called()

    def test_init_api_key_already_exists(self, client, mock_session):
        """Test initializing API key when one already exists."""
        # Mock existing API key
        mock_query = MagicMock()
        mock_query.fetchone.return_value = ("sk-existing-key",)
        mock_session.execute.return_value = mock_query

        response = client.post("/api/v1/superadmin/init-api-key")

        assert response.status_code == 409
        assert response.json["error"] == "API key already initialized"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
