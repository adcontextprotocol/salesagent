"""
Integration test specific fixtures.

These fixtures are for tests that require database and service integration.
"""

import json
import os
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.admin.app import create_app

admin_app, _ = create_app()
from src.core.database.database_session import get_db_session
from src.core.database.models import Principal, Tenant
from tests.fixtures import TenantFactory


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_tenants():
    """Clean up test tenants at the start of the test session (PostgreSQL only)."""
    original_url = os.environ.get("DATABASE_URL")

    if original_url and "postgresql" in original_url:
        # Only run cleanup in PostgreSQL (CI) environment
        from src.core.database.database_session import get_db_session
        from src.core.database.models import Creative, Tenant

        # Clean up known test tenant IDs that persist across test runs
        test_tenant_ids = ["creative_test", "a2a_creative_test"]

        with get_db_session() as session:
            for tenant_id in test_tenant_ids:
                try:
                    # First, delete any creatives for this tenant using bulk delete
                    # This avoids CASCADE issues and handles orphaned records
                    session.query(Creative).filter_by(tenant_id=tenant_id).delete(synchronize_session=False)
                    session.commit()

                    # Now delete the tenant (CASCADE will handle remaining child records)
                    tenant = session.query(Tenant).filter_by(tenant_id=tenant_id).first()
                    if tenant:
                        session.delete(tenant)
                        session.commit()
                except Exception:
                    session.rollback()

    yield


@pytest.fixture(scope="function")  # Changed to function scope for better isolation
def integration_db():
    """Provide an isolated database for each integration test.

    In CI with PostgreSQL, uses the existing database (already migrated).
    Locally with SQLite, creates an isolated temporary database per test.
    """
    import tempfile

    # Save original DATABASE_URL
    original_url = os.environ.get("DATABASE_URL")
    original_db_type = os.environ.get("DB_TYPE")

    # Check if we're using PostgreSQL (CI environment)
    # If so, use the existing database instead of trying to swap engines at runtime
    if original_url and "postgresql" in original_url:
        # CI environment: Use existing PostgreSQL database that's already migrated
        # Just ensure models are imported so they're available
        import src.core.database.models as all_models  # noqa: F401
        from src.core.database.models import Context, ObjectWorkflowMapping, WorkflowStep  # noqa: F401

        _ = (Context, WorkflowStep, ObjectWorkflowMapping)

        # Yield None to indicate we're using the existing DB
        yield None
        return

    # Local development: Create isolated SQLite database per test
    # Create a temporary database file for this test
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    # Use temporary file for testing to ensure isolation
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["DB_TYPE"] = "sqlite"  # Explicitly set DB type

    # Create the database without running migrations
    # (migrations are for production, tests create tables directly)
    from sqlalchemy import create_engine
    from sqlalchemy.orm import scoped_session, sessionmaker

    # Import ALL models first, BEFORE creating engine or Base operations
    # This ensures all tables are registered in Base.metadata
    import src.core.database.models as all_models  # noqa: F401

    # Ensure all model classes are imported and registered with Base.metadata
    # Import order matters - some models may not be registered if imported too early
    from src.core.database.models import (  # noqa: F401
        AdapterConfig,
        AuditLog,
        AuthorizedProperty,
        Base,
        Context,
        Creative,
        CreativeAssignment,
        CreativeFormat,
        FormatPerformanceMetrics,
        GAMInventory,
        GAMLineItem,
        GAMOrder,
        MediaBuy,
        ObjectWorkflowMapping,
        Principal,
        Product,
        ProductInventoryMapping,
        PropertyTag,
        PushNotificationConfig,
        Strategy,
        StrategyState,
        SyncJob,
        Tenant,
        TenantManagementConfig,
        User,
        WorkflowStep,
    )

    # Ensure workflow models are loaded (force evaluation)
    _ = (
        Context,
        WorkflowStep,
        ObjectWorkflowMapping,
        Tenant,
        Principal,
        Product,
        MediaBuy,
        Creative,
        AuthorizedProperty,
        Strategy,
        AuditLog,
        CreativeAssignment,
        TenantManagementConfig,
        PushNotificationConfig,
        User,
        CreativeFormat,
        AdapterConfig,
        GAMInventory,
        ProductInventoryMapping,
        FormatPerformanceMetrics,
        GAMOrder,
        GAMLineItem,
        SyncJob,
        StrategyState,
        PropertyTag,
    )

    # IMPORTANT: Update global database session BEFORE creating tables
    # This ensures any code that creates sessions during table creation uses the test DB
    from src.core.database import database_session

    # Save the original values
    original_engine = database_session.engine
    original_session_local = database_session.SessionLocal
    original_db_session = database_session.db_session

    # Remove any existing sessions from the scoped_session registry
    # This is critical because scoped_session caches sessions per thread
    database_session.db_session.remove()

    # Create test engine
    engine = create_engine(f"sqlite:///{db_path}")

    # Replace with test database BEFORE creating tables
    database_session.engine = engine
    database_session.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    database_session.db_session = scoped_session(database_session.SessionLocal)

    # Now create all tables (any session created will use test DB)
    Base.metadata.create_all(bind=engine)

    # Reset context manager singleton so it uses the new database session
    # This is critical because ContextManager caches a session reference
    import src.core.context_manager

    src.core.context_manager._context_manager_instance = None

    yield db_path

    # Restore original database session
    database_session.engine = original_engine
    database_session.SessionLocal = original_session_local
    database_session.db_session = original_db_session

    # Reset context manager singleton again to avoid stale references
    src.core.context_manager._context_manager_instance = None

    # Cleanup
    engine.dispose()

    # Restore original environment
    if original_url:
        os.environ["DATABASE_URL"] = original_url
    else:
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]

    if original_db_type:
        os.environ["DB_TYPE"] = original_db_type
    elif "DB_TYPE" in os.environ:
        del os.environ["DB_TYPE"]

    # Remove temporary file
    try:
        os.unlink(db_path)
    except Exception:
        pass  # Ignore cleanup errors


@pytest.fixture
def admin_client(integration_db):
    """Create test client for admin UI with proper configuration."""
    admin_app.config["TESTING"] = True
    admin_app.config["SECRET_KEY"] = "test-secret-key"
    admin_app.config["PROPAGATE_EXCEPTIONS"] = True  # Critical for catching template errors
    admin_app.config["SESSION_COOKIE_PATH"] = "/"  # Allow session cookies for all paths in tests
    admin_app.config["SESSION_COOKIE_HTTPONLY"] = False  # Allow test client to access cookies
    admin_app.config["SESSION_COOKIE_SECURE"] = False  # Allow HTTP in tests
    admin_app.config["WTF_CSRF_ENABLED"] = False  # Disable CSRF for tests
    with admin_app.test_client() as client:
        yield client


@pytest.fixture
def authenticated_admin_session(admin_client, integration_db):
    """Create an authenticated session for admin UI testing."""
    # Set up super admin configuration in database
    from src.core.database.database_session import get_db_session
    from src.core.database.models import TenantManagementConfig

    with get_db_session() as db_session:
        # Add tenant management admin email configuration
        email_config = TenantManagementConfig(config_key="super_admin_emails", config_value="test@example.com")
        db_session.add(email_config)
        db_session.commit()

    with admin_client.session_transaction() as sess:
        sess["authenticated"] = True
        sess["role"] = "super_admin"
        sess["email"] = "test@example.com"
        sess["user"] = {"email": "test@example.com", "role": "super_admin"}  # Required by require_auth decorator
        sess["is_super_admin"] = True  # Blueprint sets this
    return admin_client


@pytest.fixture
def test_tenant_with_data(integration_db):
    """Create a test tenant in the database with proper configuration."""
    tenant_data = TenantFactory.create()
    now = datetime.now(UTC)

    with get_db_session() as db_session:
        tenant = Tenant(
            tenant_id=tenant_data["tenant_id"],
            name=tenant_data["name"],
            subdomain=tenant_data["subdomain"],
            is_active=tenant_data["is_active"],
            ad_server="mock",
            auto_approve_formats=json.dumps([]),
            human_review_required=False,
            policy_settings=json.dumps({}),
            created_at=now,
            updated_at=now,
        )
        db_session.add(tenant)
        db_session.commit()

    return tenant_data


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
    from datetime import UTC, datetime

    from src.core.database.database_session import get_db_session
    from src.core.database.models import Tenant

    now = datetime.now(UTC)
    with get_db_session() as session:
        tenant = Tenant(
            tenant_id="test_tenant",
            name="Test Tenant",
            subdomain="test",
            is_active=True,
            ad_server="mock",
            max_daily_budget=10000,
            enable_axe_signals=True,
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
    from src.core.database.database_session import get_db_session

    with get_db_session() as session:
        from datetime import UTC, datetime

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
    from src.core.database.database_session import get_db_session
    from src.core.database.models import Product

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
    """Mock MCP server for integration testing (doesn't actually start a server)."""
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

    yield MockServer()


@pytest.fixture
def test_admin_app(integration_db):
    """Provide a test Admin UI app with real database."""
    # integration_db ensures database tables are created
    from src.admin.app import create_app

    app, _ = create_app()
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret-key"
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SESSION_COOKIE_PATH"] = "/"  # Allow session cookies for all paths in tests
    app.config["SESSION_COOKIE_HTTPONLY"] = False  # Allow test client to access cookies
    app.config["SESSION_COOKIE_SECURE"] = False  # Allow HTTP in tests

    yield app


@pytest.fixture
def authenticated_admin_client(test_admin_app):
    """Provide authenticated admin client with database."""
    client = test_admin_app.test_client()

    with client.session_transaction() as sess:
        sess["user"] = {"email": "admin@example.com", "name": "Admin User", "role": "super_admin"}
        sess["authenticated"] = True
        sess["role"] = "super_admin"
        sess["email"] = "admin@example.com"
        # Add test mode session keys for require_tenant_access() decorator
        sess["test_user"] = "admin@example.com"
        sess["test_user_role"] = "super_admin"
        sess["test_user_name"] = "Admin User"

    yield client


@pytest.fixture
def test_media_buy_workflow(populated_db):
    """Provide complete media buy workflow test setup."""
    from src.core.database.database_session import get_db_session
    from src.core.database.models import Creative, MediaBuy
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
    from src.core.audit_logger import AuditLogger

    logger = AuditLogger("test_tenant")

    yield logger
