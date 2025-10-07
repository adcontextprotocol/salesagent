"""Integration tests for Admin UI page rendering.

These tests ensure that admin UI pages render without errors after database schema changes.
"""

import pytest

from src.admin.app import create_app

app, _ = create_app()
from tests.fixtures import TenantFactory
from tests.utils.database_helpers import create_tenant_with_timestamps


@pytest.fixture
def client(integration_db):
    """Create test client for admin UI."""
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret-key"
    with app.test_client() as client:
        yield client


@pytest.fixture
def authenticated_session(client):
    """Create an authenticated session for testing."""
    with client.session_transaction() as sess:
        sess["authenticated"] = True
        sess["role"] = "super_admin"
        sess["email"] = "test@example.com"
    return client


@pytest.fixture
def test_tenant(integration_db):
    """Create a test tenant in the database."""

    from src.core.database.database_session import get_db_session

    tenant_data = TenantFactory.create()

    with get_db_session() as session:
        tenant = create_tenant_with_timestamps(
            tenant_id=tenant_data["tenant_id"],
            name=tenant_data["name"],
            subdomain=tenant_data["subdomain"],
            is_active=tenant_data["is_active"],
            ad_server="mock",
            auto_approve_formats=[],  # JSONType expects list, not json.dumps()
            human_review_required=False,
            policy_settings={},  # JSONType expects dict, not json.dumps()
        )
        session.add(tenant)
        session.commit()

    return tenant_data


class TestAdminUIPages:
    """Test that admin UI pages render without errors."""

    def test_list_products_page_renders(self, authenticated_session, test_tenant):
        """Test that the list products page renders successfully."""
        response = authenticated_session.get(f"/tenant/{test_tenant['tenant_id']}/products", follow_redirects=True)
        assert response.status_code == 200

    def test_create_product_page_renders(self, authenticated_session, test_tenant):
        """Test that the create product page renders successfully."""
        response = authenticated_session.get(f"/tenant/{test_tenant['tenant_id']}/products/add", follow_redirects=True)
        assert response.status_code == 200

    def test_tenant_dashboard_renders(self, authenticated_session, test_tenant):
        """Test that the tenant dashboard renders successfully (this IS the operations dashboard)."""
        response = authenticated_session.get(f"/tenant/{test_tenant['tenant_id']}", follow_redirects=True)
        assert response.status_code == 200

    def test_create_principal_page_renders(self, authenticated_session, test_tenant):
        """Test that the create principal page renders successfully."""
        response = authenticated_session.get(
            f"/tenant/{test_tenant['tenant_id']}/principals/create", follow_redirects=True
        )
        assert response.status_code == 200

    def test_settings_page_renders(self, authenticated_session, test_tenant):
        """Test that the settings page renders successfully."""
        response = authenticated_session.get(f"/tenant/{test_tenant['tenant_id']}/settings", follow_redirects=True)
        assert response.status_code == 200

    def test_admin_index_redirects(self, client):
        """Test that the admin index redirects to signup landing page when not authenticated."""
        response = client.get("/")
        assert response.status_code == 302
        assert "/signup" in response.location

    def test_login_page_renders(self, client):
        """Test that the login page renders successfully."""
        response = client.get("/login")
        assert response.status_code == 200
        assert b"Sign in" in response.data or b"Login" in response.data

    def test_404_for_unknown_tenant(self, authenticated_session):
        """Test that accessing an unknown tenant returns 404."""
        response = authenticated_session.get("/tenant/unknown_tenant/products")
        assert response.status_code in [302, 308, 404]  # 302/308 redirect to login or 404
