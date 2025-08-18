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
    from db_config import get_db_connection
    from tests.fixtures import TenantFactory, PrincipalFactory, ProductFactory

    conn = get_db_connection()

    # Create test data
    tenant = TenantFactory.create()
    principal = PrincipalFactory.create(tenant_id=tenant["tenant_id"])
    products = ProductFactory.create_batch(3, tenant_id=tenant["tenant_id"])

    # Insert test data
    conn.execute(
        """
        INSERT INTO tenants (tenant_id, name, subdomain, config, is_active)
        VALUES (?, ?, ?, ?, ?)
    """,
        (
            tenant["tenant_id"],
            tenant["name"],
            tenant["subdomain"],
            json.dumps({}),
            tenant["is_active"],
        ),
    )

    conn.execute(
        """
        INSERT INTO principals (tenant_id, principal_id, name, access_token, platform_mappings)
        VALUES (?, ?, ?, ?, ?)
    """,
        (
            principal["tenant_id"],
            principal["principal_id"],
            principal["name"],
            principal["access_token"],
            principal["platform_mappings"],
        ),
    )

    for product in products:
        conn.execute(
            """
            INSERT INTO products (tenant_id, product_id, name, formats, targeting_template)
            VALUES (?, ?, ?, ?, ?)
        """,
            (
                product["tenant_id"],
                product["product_id"],
                product["name"],
                product["formats"],
                product["targeting_template"],
            ),
        )

    conn.commit()

    yield {
        "tenant": tenant,
        "principal": principal,
        "products": products,
        "connection": conn,
    }

    conn.close()


@pytest.fixture
def mock_external_apis():
    """Mock external APIs but allow database access."""
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"status": "ok"}

        with patch("google.generativeai.configure"):
            with patch("google.generativeai.GenerativeModel") as mock_model:
                mock_instance = MagicMock()
                mock_instance.generate_content.return_value.text = (
                    "AI generated content"
                )
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

    data = populated_db
    conn = data["connection"]

    # Create media buy
    media_buy = MediaBuyFactory.create(
        tenant_id=data["tenant"]["tenant_id"],
        principal_id=data["principal"]["principal_id"],
        status="draft",
    )

    # Create creatives
    creatives = CreativeFactory.create_batch(
        2,
        tenant_id=data["tenant"]["tenant_id"],
        principal_id=data["principal"]["principal_id"],
    )

    # Insert into database
    conn.execute(
        """
        INSERT INTO media_buys (tenant_id, media_buy_id, principal_id, status, config, total_budget)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (
            media_buy["tenant_id"],
            media_buy["media_buy_id"],
            media_buy["principal_id"],
            media_buy["status"],
            media_buy["config"],
            media_buy["total_budget"],
        ),
    )

    for creative in creatives:
        conn.execute(
            """
            INSERT INTO creatives (tenant_id, creative_id, principal_id, format_id, status, content)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                creative["tenant_id"],
                creative["creative_id"],
                creative["principal_id"],
                creative["format_id"],
                creative["status"],
                creative["content"],
            ),
        )

    conn.commit()

    return {**data, "media_buy": media_buy, "creatives": creatives}


@pytest.fixture
def test_audit_logger(integration_db):
    """Provide test audit logger with database."""
    from audit_logger import AuditLogger

    logger = AuditLogger("test_tenant")

    yield logger
