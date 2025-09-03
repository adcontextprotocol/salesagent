"""Database setup for tests - ensures proper initialization."""

import os
from pathlib import Path

import pytest
from sqlalchemy import text

# Set test mode before any imports
os.environ["PYTEST_CURRENT_TEST"] = "true"


@pytest.fixture(scope="session")
def test_database_url():
    """Create a test database URL."""
    # Use in-memory SQLite for tests by default
    return os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")


@pytest.fixture(scope="session")
def test_database(test_database_url):
    """Create and initialize test database once per session."""
    # Set the database URL for the application
    os.environ["DATABASE_URL"] = test_database_url
    os.environ["DB_TYPE"] = "sqlite" if "sqlite" in test_database_url else "postgresql"

    # Run migrations if not in-memory
    if ":memory:" not in test_database_url:
        import subprocess

        result = subprocess.run(
            ["python3", "scripts/ops/migrate.py"], capture_output=True, text=True, cwd=Path(__file__).parent.parent
        )
        if result.returncode != 0:
            pytest.skip(f"Migration failed: {result.stderr}")
    else:
        # For in-memory database, create tables directly
        from src.core.database.database_session import get_engine
        from src.core.database.models import Base

        engine = get_engine()
        Base.metadata.create_all(engine)

    # Initialize with test data
    from scripts.setup.init_database import init_db

    init_db(exit_on_error=False)

    yield test_database_url

    # Cleanup is automatic for in-memory database


@pytest.fixture(scope="function")
def db_session(test_database):
    """Provide a database session for tests."""
    from src.core.database.database_session import get_db_session

    with get_db_session() as session:
        yield session
        session.rollback()  # Rollback any changes made during test


@pytest.fixture(scope="function")
def clean_db(test_database):
    """Provide a clean database for each test."""
    from src.core.database.database_session import get_engine

    engine = get_engine()

    # Clear all data but keep schema
    with engine.connect() as conn:
        # Get all table names
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        # Delete data from all tables
        for table in reversed(tables):  # Reverse to handle foreign keys
            if table != "alembic_version":  # Don't delete migration history
                conn.execute(text(f"DELETE FROM {table}"))
        conn.commit()

    # Re-initialize with test data
    from scripts.setup.init_database import init_db

    init_db(exit_on_error=False)

    yield

    # Cleanup happens automatically at function scope


@pytest.fixture
def test_tenant(db_session):
    """Create a test tenant."""
    from src.core.database.models import Tenant
    from datetime import datetime, timezone
    import uuid

    # Generate unique tenant data for each test
    unique_id = str(uuid.uuid4())[:8]
    
    # Explicitly set created_at and updated_at to avoid database constraint violations
    now = datetime.now(timezone.utc)
    tenant = Tenant(
        tenant_id=f"test_tenant_{unique_id}", 
        name=f"Test Tenant {unique_id}", 
        subdomain=f"test_{unique_id}", 
        is_active=True, 
        ad_server="mock",
        created_at=now,
        updated_at=now
    )
    db_session.add(tenant)
    db_session.commit()

    return tenant


@pytest.fixture
def test_principal(db_session, test_tenant):
    """Create a test principal."""
    from src.core.database.models import Principal
    import uuid

    unique_id = str(uuid.uuid4())[:8]
    
    principal = Principal(
        tenant_id=test_tenant.tenant_id,
        principal_id=f"test_principal_{unique_id}",
        name=f"Test Principal {unique_id}",
        access_token=f"test_token_{unique_id}",
        platform_mappings={"mock": {"advertiser_id": f"test_advertiser_{unique_id}"}},
    )
    db_session.add(principal)
    db_session.commit()

    return principal


@pytest.fixture
def test_product(db_session, test_tenant):
    """Create a test product."""
    from src.core.database.models import Product
    import uuid

    unique_id = str(uuid.uuid4())[:8]
    
    product = Product(
        product_id=f"test_product_{unique_id}",
        tenant_id=test_tenant.tenant_id,
        name=f"Test Product {unique_id}",
        formats=["display_300x250"],
        targeting_template={},
        delivery_type="guaranteed",
        is_fixed_price=True,
    )
    db_session.add(product)
    db_session.commit()

    return product


@pytest.fixture
def test_audit_log(db_session, test_tenant, test_principal):
    """Create a test audit log entry."""
    from src.core.database.models import AuditLog
    from datetime import UTC, datetime
    
    # Create a minimal audit log without strategy_id (which may not exist in all test environments)
    audit_log = AuditLog(
        tenant_id=test_tenant.tenant_id,
        principal_id=test_principal.principal_id,
        principal_name=test_principal.name,
        operation="get_products",
        timestamp=datetime.now(UTC),
        success=True,
        details={"product_count": 3, "brief": "Test query"}
        # Note: Omitting strategy_id as it may not exist in all test database schemas
    )
    db_session.add(audit_log)
    db_session.commit()
    
    return audit_log


@pytest.fixture
def test_media_buy(db_session, test_tenant, test_principal, test_product):
    """Create a test media buy."""
    from src.core.database.models import MediaBuy
    from datetime import datetime, timezone, timedelta
    import uuid
    
    unique_id = str(uuid.uuid4())[:8]
    now = datetime.now(timezone.utc)
    media_buy = MediaBuy(
        media_buy_id=f"test_media_buy_{unique_id}",
        tenant_id=test_tenant.tenant_id,
        principal_id=test_principal.principal_id,
        order_name=f"Test Order {unique_id}",
        advertiser_name=f"Test Advertiser {unique_id}",
        budget=1000.00,
        start_date=(now + timedelta(days=1)).date(),
        end_date=(now + timedelta(days=8)).date(),
        status="active",
        raw_request={"test": "data"}  # Required field
    )
    db_session.add(media_buy)
    db_session.commit()
    
    return media_buy


@pytest.fixture
def auth_headers(test_principal):
    """Get auth headers for testing."""
    return {"x-adcp-auth": test_principal.access_token}


# Import inspect only when needed
def inspect(engine):
    """Lazy import of Inspector."""
    from sqlalchemy import inspect as sqlalchemy_inspect

    return sqlalchemy_inspect(engine)
