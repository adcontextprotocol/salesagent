"""
Integration test specific fixtures.

These fixtures are for tests that require database and service integration.
"""

import pytest
import json
import os
from unittest.mock import patch, MagicMock


@pytest.fixture(scope="module")
def integration_db():
    """Provide a shared database for integration tests."""
    import tempfile

    # Create temporary database
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    # Initialize database
    from database import init_db

    init_db()

    yield db_path

    # Cleanup
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def populated_db(integration_db):
    """Provide a database populated with test data."""
    from database_session import get_db_session
    from tests.fixtures import TenantFactory, PrincipalFactory, ProductFactory
    from models import Tenant, Principal, Product

    # Create test data
    tenant_data = TenantFactory.create()
    principal_data = PrincipalFactory.create(tenant_id=tenant_data["tenant_id"])
    products_data = ProductFactory.create_batch(3, tenant_id=tenant_data["tenant_id"])

    # Insert test data using ORM
    with get_db_session() as db_session:
        # Create tenant
        tenant = Tenant(
            tenant_id=tenant_data["tenant_id"],
            name=tenant_data["name"],
            subdomain=tenant_data["subdomain"],
            config=json.dumps({}),
            is_active=tenant_data["is_active"],
        )
        db_session.add(tenant)

        # Create principal
        principal = Principal(
            tenant_id=principal_data["tenant_id"],
            principal_id=principal_data["principal_id"],
            name=principal_data["name"],
            access_token=principal_data["access_token"],
            platform_mappings=principal_data["platform_mappings"],
        )
        db_session.add(principal)

        # Create products
        for product_data in products_data:
            product = Product(
                tenant_id=product_data["tenant_id"],
                product_id=product_data["product_id"],
                name=product_data["name"],
                formats=product_data["formats"],
                targeting_template=product_data["targeting_template"],
            )
            db_session.add(product)

        db_session.commit()

    yield {
        "tenant": tenant_data,
        "principal": principal_data,
        "products": products_data,
    }


@pytest.fixture
def mock_external_apis():
    """Mock external APIs but allow database access."""
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"status": "ok"}

        with patch("google.generativeai.configure"):
            with patch("google.generativeai.GenerativeModel") as mock_model:
                mock_instance = MagicMock()
                mock_instance.generate_content.return_value.text = "AI generated content"
                mock_model.return_value = mock_instance

                yield {"requests": mock_post, "gemini": mock_instance}


@pytest.fixture
def test_server():
    """Provide a test MCP server instance."""
    from main import app as mcp_app
    from fastmcp.testing import TestClient

    # Create test client
    client = TestClient(mcp_app)

    yield client


@pytest.fixture
def test_admin_app():
    """Provide a test Admin UI app with real database."""
    from admin_ui import app

    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret-key"
    app.config["WTF_CSRF_ENABLED"] = False

    yield app


@pytest.fixture
def authenticated_admin_client(test_admin_app):
    """Provide authenticated admin client with database."""
    client = test_admin_app.test_client()

    with client.session_transaction() as sess:
        sess["authenticated"] = True
        sess["role"] = "super_admin"
        sess["email"] = "admin@example.com"

    yield client


@pytest.fixture
def test_media_buy_workflow(populated_db):
    """Provide complete media buy workflow test setup."""
    from tests.fixtures import MediaBuyFactory, CreativeFactory
    from database_session import get_db_session
    from models import MediaBuy, Creative

    data = populated_db

    # Create media buy
    media_buy_data = MediaBuyFactory.create(
        tenant_id=data["tenant"]["tenant_id"],
        principal_id=data["principal"]["principal_id"],
        status="draft",
    )

    # Create creatives
    creatives_data = CreativeFactory.create_batch(
        2,
        tenant_id=data["tenant"]["tenant_id"],
        principal_id=data["principal"]["principal_id"],
    )

    # Insert into database using ORM
    with get_db_session() as db_session:
        media_buy = MediaBuy(
            tenant_id=media_buy_data["tenant_id"],
            media_buy_id=media_buy_data["media_buy_id"],
            principal_id=media_buy_data["principal_id"],
            status=media_buy_data["status"],
            config=media_buy_data["config"],
            total_budget=media_buy_data["total_budget"],
        )
        db_session.add(media_buy)

        for creative_data in creatives_data:
            creative = Creative(
                tenant_id=creative_data["tenant_id"],
                creative_id=creative_data["creative_id"],
                principal_id=creative_data["principal_id"],
                format_id=creative_data["format_id"],
                status=creative_data["status"],
                content=creative_data["content"],
            )
            db_session.add(creative)

        db_session.commit()

    return {**data, "media_buy": media_buy_data, "creatives": creatives_data}


@pytest.fixture
def test_audit_logger(integration_db):
    """Provide test audit logger with database."""
    from audit_logger import AuditLogger

    logger = AuditLogger("test_tenant")

    yield logger
