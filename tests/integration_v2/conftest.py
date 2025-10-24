"""
Integration V2 test specific fixtures.

These fixtures are for tests migrated from integration/ that use the new
pricing_options model instead of legacy Product pricing fields.
"""

import os

import pytest

from src.admin.app import create_app

admin_app, _ = create_app()


@pytest.fixture(scope="function")
def integration_db():
    """Provide an isolated PostgreSQL database for each integration test.

    REQUIRES: PostgreSQL container running (via run_all_tests.sh ci or GitHub Actions)
    - Uses DATABASE_URL to get PostgreSQL connection info (host, port, user, password)
    - Database name in URL is ignored - creates a unique database per test (e.g., test_a3f8d92c)
    - Matches production environment exactly
    - Better multi-process support (fixes mcp_server tests)
    - Consistent JSONB behavior
    """
    import uuid

    # Save original DATABASE_URL
    original_url = os.environ.get("DATABASE_URL")
    original_db_type = os.environ.get("DB_TYPE")

    # Require PostgreSQL - no SQLite fallback
    postgres_url = os.environ.get("DATABASE_URL")
    if not postgres_url or not postgres_url.startswith("postgresql://"):
        pytest.skip(
            "Integration tests require PostgreSQL DATABASE_URL (e.g., postgresql://user:pass@localhost:5432/any_db)"
        )

    # PostgreSQL mode - create unique database per test
    unique_db_name = f"test_{uuid.uuid4().hex[:8]}"

    # Create the test database
    import re

    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

    pattern = r"postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)"
    match = re.match(pattern, postgres_url)
    if match:
        user, password, host, port_str, _ = match.groups()
        postgres_port = int(port_str)
    else:
        pytest.fail(
            f"Failed to parse DATABASE_URL: {postgres_url}\n"
            f"Expected format: postgresql://user:pass@host:port/dbname"
        )
        user, password, host, postgres_port = "adcp_user", "test_password", "localhost", 5432

    conn_params = {
        "host": host,
        "port": postgres_port,
        "user": user,
        "password": password,
        "database": "postgres",  # Connect to default db first
    }

    conn = psycopg2.connect(**conn_params)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    try:
        cur.execute(f'CREATE DATABASE "{unique_db_name}"')
    finally:
        cur.close()
        conn.close()

    os.environ["DATABASE_URL"] = f"postgresql://{user}:{password}@{host}:{postgres_port}/{unique_db_name}"
    os.environ["DB_TYPE"] = "postgresql"
    db_path = unique_db_name  # For cleanup reference

    # Create the database without running migrations
    from sqlalchemy import create_engine

    # Import ALL models first, BEFORE using Base
    import src.core.database.models as all_models  # noqa: F401

    # Explicitly ensure Context and workflow models are registered
    from src.core.database.models import (  # noqa: F401
        AuditLog,  # noqa: F401
        Base,
        Context,
        ObjectWorkflowMapping,
        WorkflowStep,
    )

    engine = create_engine(os.environ["DATABASE_URL"], echo=False)
    Base.metadata.create_all(bind=engine)

    # Reset the session maker to use the new test database
    from src.core.database.database_session import Session

    Session.configure(bind=engine)

    yield

    # Cleanup
    Session.remove()  # Close all sessions

    # Restore original environment
    if original_url is not None:
        os.environ["DATABASE_URL"] = original_url
    elif "DATABASE_URL" in os.environ:
        del os.environ["DATABASE_URL"]

    if original_db_type is not None:
        os.environ["DB_TYPE"] = original_db_type
    elif "DB_TYPE" in os.environ:
        del os.environ["DB_TYPE"]

    # Drop the test database
    conn = psycopg2.connect(**conn_params)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    try:
        # Terminate connections to the test database
        cur.execute(
            f"""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = '{unique_db_name}'
            AND pid <> pg_backend_pid()
        """
        )
        cur.execute(f'DROP DATABASE IF EXISTS "{unique_db_name}"')
    finally:
        cur.close()
        conn.close()

    # Dispose of the engine
    engine.dispose()


@pytest.fixture
def sample_tenant(integration_db):
    """Create a sample tenant for testing."""
    from decimal import Decimal

    from src.core.database.database_session import get_db_session
    from src.core.database.models import CurrencyLimit, PropertyTag, Tenant
    from tests.fixtures import TenantFactory

    tenant_data = TenantFactory.create()

    with get_db_session() as session:
        tenant = Tenant(
            tenant_id=tenant_data["tenant_id"],
            name=tenant_data["name"],
            subdomain=tenant_data["subdomain"],
            is_active=tenant_data["is_active"],
            ad_server="mock",
        )
        session.add(tenant)

        # Create required CurrencyLimit (needed for budget validation)
        currency_limit = CurrencyLimit(
            tenant_id=tenant_data["tenant_id"],
            currency_code="USD",
            max_budget_per_package=Decimal("100000.00"),
        )
        session.add(currency_limit)

        # Create required PropertyTag (needed for product property_tags)
        property_tag = PropertyTag(
            tenant_id=tenant_data["tenant_id"],
            tag_id="all_inventory",
            name="All Inventory",
            description="All available inventory",
        )
        session.add(property_tag)

        session.commit()

    return tenant_data


@pytest.fixture
def sample_products(integration_db, sample_tenant):
    """Create sample products using new pricing_options model."""
    from src.core.database.database_session import get_db_session
    from tests.conftest_shared import create_auction_product, create_test_product_with_pricing

    with get_db_session() as session:
        # Guaranteed product with fixed CPM pricing
        guaranteed = create_test_product_with_pricing(
            session=session,
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
            delivery_type="guaranteed_impressions",
            pricing_model="CPM",
            rate="15.0",
            is_fixed=True,
            currency="USD",
            countries=["US"],
            is_custom=False,
        )

        # Non-guaranteed product with auction pricing
        non_guaranteed = create_auction_product(
            session=session,
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
            pricing_model="CPM",
            floor_cpm="10.0",
            currency="USD",
            countries=["US", "CA"],
            is_custom=False,
            price_guidance={"floor": 10.0, "p50": 20.0, "p75": 30.0, "p90": 40.0},
        )

        session.commit()

        return [guaranteed.product_id, non_guaranteed.product_id]


@pytest.fixture
def sample_principal(integration_db, sample_tenant):
    """Create a sample principal (advertiser) for testing."""
    from src.core.database.database_session import get_db_session
    from src.core.database.models import Principal
    from tests.fixtures import PrincipalFactory

    principal_data = PrincipalFactory.create(tenant_id=sample_tenant["tenant_id"])

    with get_db_session() as session:
        principal = Principal(
            tenant_id=sample_tenant["tenant_id"],
            principal_id=principal_data["principal_id"],
            name=principal_data["name"],
            access_token=principal_data["access_token"],
        )
        session.add(principal)
        session.commit()

    return principal_data
