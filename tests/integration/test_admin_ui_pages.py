"""Integration tests for Admin UI page rendering.

These tests ensure that admin UI pages render without errors after database schema changes.
"""

import pytest
from unittest.mock import patch, MagicMock
import sys
import os
sys.path.insert(0, '.')

# Set test database for isolation
os.environ['DATABASE_URL'] = 'sqlite:///test_admin_ui.db'

from admin_ui import app
from tests.fixtures import TenantFactory, ProductFactory, PrincipalFactory
from db_config import get_db_connection
from database_schema import init_database
from migrate import run_migrations


@pytest.fixture(scope="module")
def setup_test_db():
    """Set up test database once for the module."""
    # Initialize database
    init_database()
    # Run migrations
    run_migrations()
    yield
    # Cleanup
    if os.path.exists('test_admin_ui.db'):
        os.remove('test_admin_ui.db')


@pytest.fixture
def client(setup_test_db):
    """Create test client for admin UI."""
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key'
    with app.test_client() as client:
        yield client


@pytest.fixture
def authenticated_session(client):
    """Create an authenticated session for testing."""
    with client.session_transaction() as sess:
        sess['user'] = 'test@example.com'
        sess['role'] = 'super_admin'
        sess['name'] = 'Test User'
        sess['picture'] = 'http://example.com/picture.jpg'


@pytest.mark.requires_db
class TestAdminUIPages:
    """Test that admin UI pages render without database errors."""
    
    def test_list_products_page_renders(self, client, authenticated_session):
        """Test that the products list page renders without errors."""
        # Create test tenant
        tenant = TenantFactory.create()
        
        # Create some test products
        ProductFactory.create(tenant_id=tenant['tenant_id'])
        ProductFactory.create(tenant_id=tenant['tenant_id'])
        
        # Test the products page
        response = client.get(f"/tenant/{tenant['tenant_id']}/products")
        
        # Should either succeed or redirect to login
        assert response.status_code in [200, 302], f"Unexpected status: {response.status_code}"
        
        # If redirected to login, authenticate and try again
        if response.status_code == 302:
            with client.session_transaction() as sess:
                sess['user'] = 'test@example.com'
                sess['role'] = 'super_admin'
                sess['name'] = 'Test User'
                sess['picture'] = 'http://example.com/picture.jpg'
            
            response = client.get(f"/tenant/{tenant['tenant_id']}/products")
            assert response.status_code == 200, f"Failed to load products page: {response.data}"
    
    def test_policy_settings_page_renders(self, client, authenticated_session):
        """Test that the policy settings page renders without errors."""
        # Create test tenant
        tenant = TenantFactory.create()
        
        # Test the policy page
        response = client.get(f"/tenant/{tenant['tenant_id']}/policy")
        
        # Should either succeed or redirect to login
        assert response.status_code in [200, 302], f"Unexpected status: {response.status_code}"
        
        # If redirected to login, authenticate and try again
        if response.status_code == 302:
            with client.session_transaction() as sess:
                sess['user'] = 'test@example.com'
                sess['role'] = 'super_admin'
                sess['name'] = 'Test User'
                sess['picture'] = 'http://example.com/picture.jpg'
            
            response = client.get(f"/tenant/{tenant['tenant_id']}/policy")
            assert response.status_code == 200, f"Failed to load policy page: {response.data}"
    
    def test_pages_use_new_schema_not_config_column(self, client, authenticated_session):
        """Test that pages use the new schema columns instead of the old config column.
        
        This test verifies that after the migration from a single 'config' column
        to individual columns, the admin UI pages correctly use the new schema.
        """
        # Create test tenant
        tenant = TenantFactory.create()
        
        # Test that we're NOT using the old 'config' column
        conn = get_db_connection()
        
        # The old query that should NOT be used anymore
        try:
            cursor = conn.execute("SELECT config FROM tenants WHERE tenant_id = ?", (tenant['tenant_id'],))
            # If this succeeds, it means the config column still exists (which is wrong after migration)
            pytest.fail("The 'config' column should not exist after migration to individual columns")
        except Exception as e:
            # This is expected - the config column should not exist
            assert "config" in str(e).lower() or "no such column" in str(e).lower(), \
                f"Expected error about missing 'config' column, got: {e}"
        
        # Test that the new columns DO exist
        cursor = conn.execute("""
            SELECT ad_server, max_daily_budget, enable_aee_signals, 
                   human_review_required, admin_token
            FROM tenants WHERE tenant_id = ?
        """, (tenant['tenant_id'],))
        row = cursor.fetchone()
        assert row is not None, "Should be able to query new schema columns"
        
        conn.close()
        
        # And the pages should work with the new schema
        with client.session_transaction() as sess:
            sess['user'] = 'test@example.com'
            sess['role'] = 'super_admin'
            sess['name'] = 'Test User'
        
        response = client.get(f"/tenant/{tenant['tenant_id']}/products")
        # Should not return 500 error
        assert response.status_code != 500, f"Page returned 500 error - likely database schema issue"