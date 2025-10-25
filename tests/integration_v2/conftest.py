"""
Integration V2 test specific fixtures.

These fixtures are for tests migrated from integration/ that use the new
pricing_options model instead of legacy Product pricing fields.
"""

import os
from decimal import Decimal
from typing import Any

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

    # Reset engine BEFORE creating new database to close all old connections
    from sqlalchemy.orm import scoped_session, sessionmaker

    # Import ALL models first, BEFORE using Base
    import src.core.database.models as all_models  # noqa: F401
    from src.core.database.database_session import reset_engine

    # Explicitly ensure Context and workflow models are registered
    from src.core.database.models import (  # noqa: F401
        AuditLog,  # noqa: F401
        Base,
        Context,
        ObjectWorkflowMapping,
        WorkflowStep,
    )

    reset_engine()

    # Reset context manager singleton so it uses the new database session
    # This is critical because ContextManager caches a session reference
    import src.core.context_manager

    src.core.context_manager._context_manager_instance = None

    engine = create_engine(os.environ["DATABASE_URL"], echo=False)
    Base.metadata.create_all(bind=engine)

    # Now update the globals to use our test engine
    import src.core.database.database_session as db_session_module

    db_session_module._engine = engine
    db_session_module._session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db_session_module._scoped_session = scoped_session(db_session_module._session_factory)

    yield

    # Reset engine to clean up test database connections
    reset_engine()

    # Reset context manager singleton again to avoid stale references
    src.core.context_manager._context_manager_instance = None

    # Cleanup
    engine.dispose()

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
    from src.core.database.models import AuthorizedProperty, CurrencyLimit, PropertyTag, Tenant
    from tests.fixtures import TenantFactory

    tenant_data = TenantFactory.create()

    with get_db_session() as session:
        tenant = Tenant(
            tenant_id=tenant_data["tenant_id"],
            name=tenant_data["name"],
            subdomain=tenant_data["subdomain"],
            is_active=tenant_data["is_active"],
            ad_server="mock",
            # Required: Access control configuration
            authorized_emails=["test@example.com"],
        )
        session.add(tenant)

        # Create required CurrencyLimit (needed for budget validation)
        currency_limit = CurrencyLimit(
            tenant_id=tenant_data["tenant_id"],
            currency_code="USD",
            min_package_budget=Decimal("1.00"),
            max_daily_package_spend=Decimal("100000.00"),
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

        # Create required AuthorizedProperty (needed for setup validation)
        authorized_property = AuthorizedProperty(
            tenant_id=tenant_data["tenant_id"],
            property_id="test_property_1",
            property_type="website",
            name="Test Property",
            identifiers=[{"type": "domain", "value": "example.com"}],
            publisher_domain="example.com",
            verification_status="verified",
        )
        session.add(authorized_property)

        session.commit()

    return tenant_data


@pytest.fixture
def sample_products(integration_db, sample_tenant):
    """Create sample products using new pricing_options model."""
    from src.core.database.database_session import get_db_session

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
                    "agent_url": "https://test.com",
                    "id": "display_300x250",
                }
            ],
            targeting_template={"geo_country": {"values": ["US"], "required": False}},
            delivery_type="guaranteed",
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
                    "agent_url": "https://test.com",
                    "id": "video_15s",
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
            platform_mappings=principal_data.get("platform_mappings", {}),
        )
        session.add(principal)
        session.commit()

    return principal_data


# ============================================================================
# Setup Helper Functions
# ============================================================================


def add_required_setup_data(session, tenant_id: str):
    """Add required setup data for a tenant to pass setup validation.

    This helper ensures tenants have:
    1. Access control (authorized_emails)
    2. Authorized property (for AdCP verification)
    3. Currency limit (for budget validation)
    4. Property tag (for product configuration)

    Call this in test fixtures to avoid "Setup incomplete" errors.
    """
    from decimal import Decimal

    from sqlalchemy import select

    from src.core.database.models import AuthorizedProperty, CurrencyLimit, PropertyTag, Tenant

    # Update tenant with access control
    stmt = select(Tenant).filter_by(tenant_id=tenant_id)
    tenant = session.scalars(stmt).first()
    if tenant and not tenant.authorized_emails:
        tenant.authorized_emails = ["test@example.com"]

    # Create AuthorizedProperty if not exists
    stmt = select(AuthorizedProperty).filter_by(tenant_id=tenant_id)
    if not session.scalars(stmt).first():
        authorized_property = AuthorizedProperty(
            tenant_id=tenant_id,
            property_id=f"{tenant_id}_property_1",
            property_type="website",
            name="Test Property",
            identifiers=[{"type": "domain", "value": "example.com"}],
            publisher_domain="example.com",
            verification_status="verified",
        )
        session.add(authorized_property)

    # Create CurrencyLimit if not exists
    stmt = select(CurrencyLimit).filter_by(tenant_id=tenant_id, currency_code="USD")
    if not session.scalars(stmt).first():
        currency_limit = CurrencyLimit(
            tenant_id=tenant_id,
            currency_code="USD",
            min_package_budget=Decimal("1.00"),
            max_daily_package_spend=Decimal("100000.00"),
        )
        session.add(currency_limit)

    # Create PropertyTag if not exists
    stmt = select(PropertyTag).filter_by(tenant_id=tenant_id, tag_id="all_inventory")
    if not session.scalars(stmt).first():
        property_tag = PropertyTag(
            tenant_id=tenant_id,
            tag_id="all_inventory",
            name="All Inventory",
            description="All available inventory",
        )
        session.add(property_tag)


# ============================================================================
# Pricing Helper Functions
# ============================================================================
# These helpers provide a consistent API for creating Products with
# pricing_options. They will break if Product/PricingOption schema changes
# (intentional - ensures tests stay up to date with migrations).


def create_test_product_with_pricing(
    session,
    tenant_id: str,
    product_id: str | None = None,
    name: str = "Test Product",
    pricing_model: str = "CPM",
    rate: Decimal | float | str = "15.00",
    is_fixed: bool = True,
    currency: str = "USD",
    min_spend_per_package: Decimal | float | str | None = None,
    price_guidance: dict | None = None,
    formats: list[dict[str, str]] | None = None,
    targeting_template: dict | None = None,
    delivery_type: str = "guaranteed_impressions",
    property_tags: list[str] | None = None,
    **product_kwargs: Any,
):
    """Create a Product with pricing_options using the new pricing model.

    This helper provides a simple API that mirrors the old Product(is_fixed_price=True, cpm=15.0)
    pattern but uses the new PricingOption table.

    Args:
        session: SQLAlchemy session
        tenant_id: Tenant ID
        product_id: Product ID (auto-generated if None)
        name: Product name
        pricing_model: One of: CPM, VCPM, CPC, FLAT_RATE, CPV, CPCV, CPP
        rate: Price rate (converted to Decimal)
        is_fixed: True for fixed pricing, False for auction
        currency: Currency code (default: USD)
        min_spend_per_package: Minimum spend per package (optional)
        formats: Creative formats (default: standard 300x250)
        targeting_template: Targeting template (default: empty)
        delivery_type: Delivery type (default: guaranteed_impressions)
        property_tags: Property tags (default: ["all_inventory"])
        **product_kwargs: Additional Product model fields

    Returns:
        Product instance with pricing_options populated

    Example:
        # Old pattern (BROKEN):
        product = Product(tenant_id="test", is_fixed_price=True, cpm=15.0)

        # New pattern (WORKS):
        product = create_test_product_with_pricing(
            session, tenant_id="test", pricing_model="CPM", rate=15.0
        )
    """
    import uuid

    from src.core.database.models import PricingOption, Product

    # Auto-generate product_id if not provided
    if product_id is None:
        product_id = f"test_product_{uuid.uuid4().hex[:8]}"

    # Default formats (standard display ad)
    if formats is None:
        formats = [{"agent_url": "https://test.com", "id": "300x250"}]

    # Default targeting template
    if targeting_template is None:
        targeting_template = {}

    # Default property_tags (required by AdCP spec: must have properties OR property_tags)
    if property_tags is None and "properties" not in product_kwargs:
        property_tags = ["all_inventory"]

    # Convert rate to Decimal
    if isinstance(rate, str):
        rate_decimal = Decimal(rate)
    elif isinstance(rate, float):
        rate_decimal = Decimal(str(rate))
    else:
        rate_decimal = rate

    # Convert min_spend to Decimal if provided
    min_spend_decimal = None
    if min_spend_per_package is not None:
        if isinstance(min_spend_per_package, str):
            min_spend_decimal = Decimal(min_spend_per_package)
        elif isinstance(min_spend_per_package, float):
            min_spend_decimal = Decimal(str(min_spend_per_package))
        else:
            min_spend_decimal = min_spend_per_package

    # Create Product
    product = Product(
        tenant_id=tenant_id,
        product_id=product_id,
        name=name,
        formats=formats,
        targeting_template=targeting_template,
        delivery_type=delivery_type,
        property_tags=property_tags,
        **product_kwargs,
    )
    session.add(product)
    session.flush()  # Get product into session before adding pricing_options

    # Create PricingOption
    # Convert pricing_model to lowercase for AdCP spec compliance
    pricing_model_lower = pricing_model.lower() if isinstance(pricing_model, str) else pricing_model
    pricing_option = PricingOption(
        tenant_id=tenant_id,
        product_id=product_id,
        pricing_model=pricing_model_lower,
        rate=rate_decimal,
        currency=currency,
        is_fixed=is_fixed,
        price_guidance=price_guidance,
        min_spend_per_package=min_spend_decimal,
    )
    session.add(pricing_option)
    session.flush()  # Ensure pricing_option is persisted

    # Refresh product to load relationship
    session.refresh(product)

    return product


def create_auction_product(
    session,
    tenant_id: str,
    product_id: str | None = None,
    name: str = "Auction Product",
    pricing_model: str = "CPM",
    floor_cpm: Decimal | float | str = "1.00",
    currency: str = "USD",
    **kwargs: Any,
):
    """Create a Product with auction pricing (is_fixed=False).

    Convenience wrapper for create_test_product_with_pricing with is_fixed=False.

    Args:
        session: SQLAlchemy session
        tenant_id: Tenant ID
        product_id: Product ID (auto-generated if None)
        name: Product name
        pricing_model: Pricing model (default: CPM)
        floor_cpm: Minimum floor price for auction
        currency: Currency code (default: USD)
        **kwargs: Additional arguments passed to create_test_product_with_pricing

    Returns:
        Product with auction pricing
    """
    # Auction products require price_guidance per AdCP spec (if not already provided)
    if "price_guidance" not in kwargs:
        floor_value = float(floor_cpm)
        kwargs["price_guidance"] = {
            "floor": floor_value,
            "p50": floor_value * 1.5,  # Median is 50% above floor
            "p75": floor_value * 2.0,  # 75th percentile is 2x floor
            "p90": floor_value * 2.5,  # 90th percentile is 2.5x floor
        }

    return create_test_product_with_pricing(
        session=session,
        tenant_id=tenant_id,
        product_id=product_id,
        name=name,
        pricing_model=pricing_model,
        rate=floor_cpm,
        is_fixed=False,
        currency=currency,
        **kwargs,
    )


def create_flat_rate_product(
    session,
    tenant_id: str,
    product_id: str | None = None,
    name: str = "Flat Rate Product",
    rate: Decimal | float | str = "10000.00",
    currency: str = "USD",
    **kwargs: Any,
):
    """Create a Product with flat-rate pricing.

    Convenience wrapper for FLAT_RATE pricing model.

    Args:
        session: SQLAlchemy session
        tenant_id: Tenant ID
        product_id: Product ID (auto-generated if None)
        name: Product name
        rate: Total campaign cost
        currency: Currency code (default: USD)
        **kwargs: Additional arguments passed to create_test_product_with_pricing

    Returns:
        Product with flat-rate pricing
    """
    return create_test_product_with_pricing(
        session=session,
        tenant_id=tenant_id,
        product_id=product_id,
        name=name,
        pricing_model="FLAT_RATE",
        rate=rate,
        is_fixed=True,
        currency=currency,
        delivery_type="sponsorship",  # FLAT_RATE typically uses sponsorship
        **kwargs,
    )


# ============================================================================
# End Pricing Helper Functions
# ============================================================================
