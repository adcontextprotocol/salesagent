"""
Integration test specific fixtures.

These fixtures are for tests that require database and service integration.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(scope="module")
def integration_db():
    """Provide a shared database for integration tests."""

    # Use in-memory SQLite for testing (temporary until full PostgreSQL migration)
    # This creates tables using SQLAlchemy ORM
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.environ["DB_TYPE"] = "sqlite"  # Explicitly set DB type

    # Initialize database tables using SQLAlchemy
    from database_session import engine
    from models import Base

    # Create all tables
    Base.metadata.create_all(bind=engine)

    # Initialize with default data
    from database import init_db

    init_db()

    yield "memory"

    # Cleanup is automatic with in-memory database


@pytest.fixture
def populated_db(integration_db):
    """Provide a database populated with test data."""
    from tests.fixtures import PrincipalFactory, ProductFactory, TenantFactory

    # Create test data
    tenant_data = TenantFactory.create()
    PrincipalFactory.create(tenant_id=tenant_data["tenant_id"])
    ProductFactory.create_batch(3, tenant_id=tenant_data["tenant_id"])


@pytest.fixture
def sample_tenant(integration_db):
    """Create a sample tenant for testing."""
    from datetime import datetime

    from database_session import get_db_session
    from models import Tenant

    now = datetime.now(UTC)
    with get_db_session() as session:
        tenant = Tenant(
            tenant_id="test_tenant",
            name="Test Tenant",
            subdomain="test",
            is_active=True,
            ad_server="mock",
            max_daily_budget=10000,
            enable_aee_signals=True,
            authorized_emails=["test@example.com"],
            authorized_domains=["example.com"],
            auto_approve_formats=["display_300x250"],
            human_review_required=False,
            admin_token="test_admin_token",
            created_at=now,
            updated_at=now,
        )
        session.add(tenant)
        session.commit()

        return {
            "tenant_id": tenant.tenant_id,
            "name": tenant.name,
            "admin_token": tenant.admin_token,
        }


@pytest.fixture
def sample_principal(integration_db, sample_tenant):
    """Create a sample principal with valid platform mappings."""
    from database_session import get_db_session
    from models import Principal

    with get_db_session() as session:
        from datetime import datetime

        now = datetime.now(UTC)
        principal = Principal(
            tenant_id=sample_tenant["tenant_id"],
            principal_id="test_principal",
            name="Test Advertiser",
            access_token="test_token_12345",
            platform_mappings={"mock": {"id": "test_advertiser"}},
            created_at=now,
        )
        session.add(principal)
        session.commit()

        return {
            "principal_id": principal.principal_id,
            "name": principal.name,
            "access_token": principal.access_token,
        }


@pytest.fixture
def sample_products(integration_db, sample_tenant):
    """Create sample products that comply with AdCP protocol."""
    from database_session import get_db_session
    from models import Product

    with get_db_session() as session:
        products = [
            Product(
                tenant_id=sample_tenant["tenant_id"],
                product_id="guaranteed_display",
                name="Guaranteed Display Ads",
                description="Premium guaranteed display advertising",
                formats=[
                    {
                        "format_id": "display_300x250",
                        "name": "Medium Rectangle",
                        "type": "display",
                        "description": "Standard display format",
                        "width": 300,
                        "height": 250,
                        "delivery_options": {"hosted": None},
                    }
                ],
                targeting_template={"geo_country": {"values": ["US"], "required": False}},
                delivery_type="guaranteed",
                is_fixed_price=True,
                cpm=15.0,
                is_custom=False,
                countries=["US"],
            ),
            Product(
                tenant_id=sample_tenant["tenant_id"],
                product_id="non_guaranteed_video",
                name="Non-Guaranteed Video",
                description="Programmatic video advertising",
                formats=[
                    {
                        "format_id": "video_15s",
                        "name": "15 Second Video",
                        "type": "video",
                        "description": "Short form video",
                        "duration": 15,
                        "delivery_options": {"vast": {"mime_types": ["video/mp4"]}},
                    }
                ],
                targeting_template={},
                delivery_type="non_guaranteed",
                is_fixed_price=False,
                price_guidance={"floor": 10.0, "p50": 20.0, "p75": 30.0, "p90": 40.0},
                is_custom=False,
                countries=["US", "CA"],
            ),
        ]

        for product in products:
            session.add(product)
        session.commit()

        return [p.product_id for p in products]

    # Insert test data using ORM
    with get_db_session() as db_session:
        # Create tenant
        from datetime import datetime

        now = datetime.now(UTC)
        tenant = Tenant(
            tenant_id=tenant_data["tenant_id"],
            name=tenant_data["name"],
            subdomain=tenant_data["subdomain"],
            config=json.dumps({}),
            is_active=tenant_data["is_active"],
            created_at=now,
            updated_at=now,
        )
        db_session.add(tenant)

        # Create principal
        principal = Principal(
            tenant_id=principal_data["tenant_id"],
            principal_id=principal_data["principal_id"],
            name=principal_data["name"],
            access_token=principal_data["access_token"],
            platform_mappings=principal_data["platform_mappings"],
            created_at=now,
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


@pytest.fixture(scope="session")
def mcp_server():
    """Start the MCP server for integration testing."""
    import socket

    # Find an available port
    def get_free_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port

    port = get_free_port()

    # Start the server in a subprocess
    env = os.environ.copy()
    env["ADCP_SALES_PORT"] = str(port)
    env["DATABASE_URL"] = "sqlite:///:memory:"

    # Use a mock server process for testing
    class MockServer:
        def __init__(self):
            self.port = 8080  # Default MCP port

    return MockServer()

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
    from database_session import get_db_session
    from models import Creative, MediaBuy
    from tests.fixtures import CreativeFactory, MediaBuyFactory

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
