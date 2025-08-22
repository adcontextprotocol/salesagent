"""
Global pytest configuration and fixtures for all tests.

This file provides fixtures available to all test modules.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import database fixtures for all tests
from tests.conftest_db import *  # noqa: F401,F403

# Set testing environment
os.environ["ADCP_TESTING"] = "true"

# Only set DATABASE_URL if not already set (allows CI to override)
# Use in-memory database by default to avoid test pollution
if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"

# Set default test environment variables
os.environ.setdefault("GEMINI_API_KEY", "test_key_for_mocking")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test_client_id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test_client_secret")
os.environ.setdefault("SUPER_ADMIN_EMAILS", "test@example.com")

# Import fixtures modules
from tests.fixtures import (
    CreativeFactory,
    MediaBuyFactory,
    MockAdapter,
    MockDatabase,
    MockGeminiService,
    MockOAuthProvider,
    PrincipalFactory,
    ProductFactory,
    RequestBuilder,
    ResponseBuilder,
    TargetingBuilder,
    TenantFactory,
)

# ============================================================================
# Database Fixtures
# ============================================================================


@pytest.fixture
def mock_db():
    """Provide a mock database connection."""
    return MockDatabase()


@pytest.fixture
def mock_db_with_data(mock_db):
    """Provide a mock database with sample data."""
    # Add sample tenant
    tenant = TenantFactory.create()
    mock_db.set_query_result("SELECT.*FROM tenants", [tenant])

    # Add sample principal
    principal = PrincipalFactory.create(tenant_id=tenant["tenant_id"])
    mock_db.set_query_result("SELECT.*FROM principals", [principal])

    # Add sample products
    products = ProductFactory.create_batch(3, tenant_id=tenant["tenant_id"])
    mock_db.set_query_result("SELECT.*FROM products", products)

    return mock_db


@pytest.fixture
def test_db_path():
    """Provide a temporary test database path."""
    # Create a unique temporary file for each test
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    yield db_path

    # Cleanup
    if os.path.exists(db_path):
        try:
            os.unlink(db_path)
        except Exception:
            pass  # Ignore cleanup errors


@pytest.fixture
def db_session(test_db_path):
    """Provide a test database session with isolated data."""
    # Save original DATABASE_URL
    original_url = os.environ.get("DATABASE_URL")

    # Use temporary database for this test
    os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path}"

    # Initialize database
    from src.core.database.database import init_db

    init_db()

    # Create session
    from src.core.database.db_config import get_db_connection

    conn = get_db_connection()

    yield conn

    # Cleanup
    conn.close()

    # Restore original DATABASE_URL
    if original_url:
        os.environ["DATABASE_URL"] = original_url
    else:
        os.environ["DATABASE_URL"] = "sqlite:///:memory:"


# ============================================================================
# Factory Fixtures
# ============================================================================


@pytest.fixture
def tenant_factory():
    """Provide tenant factory."""
    return TenantFactory


@pytest.fixture
def principal_factory():
    """Provide principal factory."""
    return PrincipalFactory


@pytest.fixture
def product_factory():
    """Provide product factory."""
    return ProductFactory


@pytest.fixture
def media_buy_factory():
    """Provide media buy factory."""
    return MediaBuyFactory


@pytest.fixture
def creative_factory():
    """Provide creative factory."""
    return CreativeFactory


@pytest.fixture
def sample_tenant():
    """Provide a sample tenant."""
    return TenantFactory.create(tenant_id="test_tenant", name="Test Publisher", subdomain="test")


@pytest.fixture
def sample_principal(sample_tenant):
    """Provide a sample principal."""
    return PrincipalFactory.create(
        tenant_id=sample_tenant["tenant_id"],
        principal_id="test_principal",
        name="Test Advertiser",
        access_token="test_token_123",
    )


@pytest.fixture
def sample_products(sample_tenant):
    """Provide sample products."""
    return ProductFactory.create_batch(3, tenant_id=sample_tenant["tenant_id"])


# ============================================================================
# Mock Service Fixtures
# ============================================================================


@pytest.fixture
def mock_adapter():
    """Provide a mock ad server adapter."""
    return MockAdapter()


@pytest.fixture
def mock_gemini():
    """Provide a mock Gemini AI service."""
    return MockGeminiService()


@pytest.fixture
def mock_oauth():
    """Provide a mock OAuth provider."""
    return MockOAuthProvider()


@pytest.fixture
def mock_gemini_env(mock_gemini):
    """Mock Gemini environment."""
    with patch("google.generativeai.configure"):
        with patch("google.generativeai.GenerativeModel") as mock_model:
            mock_model.return_value = mock_gemini
            yield mock_gemini


# ============================================================================
# Builder Fixtures
# ============================================================================


@pytest.fixture
def request_builder():
    """Provide request builder."""
    return RequestBuilder()


@pytest.fixture
def response_builder():
    """Provide response builder."""
    return ResponseBuilder()


@pytest.fixture
def targeting_builder():
    """Provide targeting builder."""
    return TargetingBuilder()


# ============================================================================
# Authentication Fixtures
# ============================================================================


@pytest.fixture
def auth_headers(sample_principal):
    """Provide authentication headers."""
    return {"x-adcp-auth": sample_principal["access_token"]}


@pytest.fixture
def admin_session():
    """Provide admin session data."""
    return {"authenticated": True, "role": "super_admin", "email": "admin@example.com", "name": "Admin User"}


@pytest.fixture
def tenant_admin_session(sample_tenant):
    """Provide tenant admin session data."""
    return {
        "authenticated": True,
        "role": "tenant_admin",
        "tenant_id": sample_tenant["tenant_id"],
        "email": "tenant.admin@example.com",
        "name": "Tenant Admin",
    }


# ============================================================================
# Flask App Fixtures
# ============================================================================


@pytest.fixture
def flask_app():
    """Provide Flask test app."""
    # Mock database before importing admin app
    with patch("database_session.get_db_session") as mock_get_session:
        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = None
        mock_session.query.return_value.filter_by.return_value.all.return_value = []
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_session.query.return_value.filter.return_value.all.return_value = []
        mock_session.query.return_value.all.return_value = []
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)
        mock_get_session.return_value = mock_session

        # Mock inventory service database session
        with patch("gam_inventory_service.db_session") as mock_inv_session:
            mock_inv_session.query.return_value.filter.return_value.all.return_value = []
            mock_inv_session.close = MagicMock()
            mock_inv_session.remove = MagicMock()

            from src.admin.app import create_app

            app, _ = create_app()
            app.config["TESTING"] = True
            app.config["SECRET_KEY"] = "test-secret-key"
            return app


@pytest.fixture
def flask_client(flask_app):
    """Provide Flask test client."""
    return flask_app.test_client()


@pytest.fixture
def authenticated_client(flask_client, admin_session):
    """Provide authenticated Flask client."""
    with flask_client.session_transaction() as sess:
        sess.update(admin_session)
    return flask_client


# ============================================================================
# MCP Context Fixtures
# ============================================================================


@pytest.fixture
def mcp_context(auth_headers):
    """Provide MCP context object."""

    class MockContext:
        def __init__(self, headers):
            self.headers = headers

        def get_header(self, name, default=None):
            return self.headers.get(name, default)

    return MockContext(auth_headers)


# ============================================================================
# Test Data Fixtures
# ============================================================================


@pytest.fixture
def sample_media_buy_request():
    """Provide sample media buy request."""
    return {
        "product_ids": ["prod_1", "prod_2"],
        "total_budget": 10000.0,
        "flight_start_date": "2025-02-01",
        "flight_end_date": "2025-02-28",
        "targeting_overlay": {"geo_country_any_of": ["US"], "device_type_any_of": ["desktop", "mobile"]},
    }


@pytest.fixture
def sample_creative_content():
    """Provide sample creative content."""
    return {
        "headline": "Test Advertisement",
        "body": "This is a test ad for automated testing.",
        "cta_text": "Learn More",
        "image_url": "https://example.com/test-ad.jpg",
        "click_url": "https://example.com/landing",
        "advertiser": "Test Company",
    }


@pytest.fixture
def fixture_data_path():
    """Provide path to fixture data directory."""
    return Path(__file__).parent / "fixtures" / "data"


@pytest.fixture
def load_fixture_json():
    """Provide function to load fixture JSON files."""

    def _load(filename):
        fixture_path = Path(__file__).parent / "fixtures" / "data" / filename
        with open(fixture_path) as f:
            return json.load(f)

    return _load


# ============================================================================
# Cleanup Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def cleanup_env():
    """Clean up environment after each test."""
    # Store original env
    original_env = os.environ.copy()

    yield

    # Restore original env (but keep testing flags)
    test_vars = [
        "ADCP_TESTING",
        "DATABASE_URL",
        "GEMINI_API_KEY",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "SUPER_ADMIN_EMAILS",
    ]

    for key in list(os.environ.keys()):
        if key not in original_env and key not in test_vars:
            del os.environ[key]


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singleton instances between tests."""
    # Reset any singleton instances that might carry state
    yield

    # Add any singleton reset logic here


# ============================================================================
# Performance Fixtures
# ============================================================================


@pytest.fixture
def benchmark(request):
    """Simple benchmark fixture for performance testing."""
    import time

    start_time = time.time()

    yield

    duration = time.time() - start_time
    print(f"\n{request.node.name} took {duration:.3f}s")

    # Mark as slow if > 5 seconds
    if duration > 5:
        request.node.add_marker(pytest.mark.slow)
