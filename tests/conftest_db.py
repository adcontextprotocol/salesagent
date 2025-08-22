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

    tenant = Tenant(tenant_id="test_tenant", name="Test Tenant", subdomain="test", is_active=True, ad_server="mock")
    db_session.add(tenant)
    db_session.commit()

    return tenant


@pytest.fixture
def test_principal(db_session, test_tenant):
    """Create a test principal."""
    from src.core.database.models import Principal

    principal = Principal(
        tenant_id=test_tenant.tenant_id,
        principal_id="test_principal",
        name="Test Principal",
        access_token="test_token_12345",
        platform_mappings={"mock": {"advertiser_id": "test_advertiser"}},
    )
    db_session.add(principal)
    db_session.commit()

    return principal


@pytest.fixture
def test_product(db_session, test_tenant):
    """Create a test product."""
    from src.core.database.models import Product

    product = Product(
        product_id="test_product",
        tenant_id=test_tenant.tenant_id,
        name="Test Product",
        formats=["display_300x250"],
        targeting_template={},
        delivery_type="guaranteed",
        is_fixed_price=True,
    )
    db_session.add(product)
    db_session.commit()

    return product


@pytest.fixture
def auth_headers(test_principal):
    """Get auth headers for testing."""
    return {"x-adcp-auth": test_principal.access_token}


# Import inspect only when needed
def inspect(engine):
    """Lazy import of Inspector."""
    from sqlalchemy import inspect as sqlalchemy_inspect

    return sqlalchemy_inspect(engine)
