"""Integration tests for format conversion logic during media buy approval.

Tests the conversion of product.formats (FormatReference/dict) to MediaPackage.format_ids
(FormatId objects) in execute_approved_media_buy function.

This tests the critical format conversion logic at lines 391-452 of media_buy_create.py.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from src.core.database.database_session import get_db_session
from src.core.database.models import (
    CurrencyLimit,
    MediaBuy,
    PricingOption,
    Principal,
    Product,
    PropertyTag,
    Tenant,
)
from src.core.tools.media_buy_create import execute_approved_media_buy


@pytest.fixture
def test_tenant(integration_db):
    """Create test tenant with mock ad server."""
    tenant_id = "test_format_conversion"
    with get_db_session() as session:
        tenant = Tenant(
            tenant_id=tenant_id,
            name="Format Test Tenant",
            subdomain="formattest",
            is_active=True,
            ad_server="mock",
        )
        session.add(tenant)
        session.commit()

    yield tenant_id

    # Cleanup
    with get_db_session() as session:
        stmt = select(Tenant).filter_by(tenant_id=tenant_id)
        tenant = session.scalars(stmt).first()
        if tenant:
            session.delete(tenant)
            session.commit()


@pytest.fixture
def test_currency_limit(integration_db, test_tenant):
    """Create required CurrencyLimit for budget validation.

    Per CLAUDE.md "Database Initialization Dependencies":
    Products require CurrencyLimit for budget validation in media buys.
    """
    with get_db_session() as session:
        currency_limit = CurrencyLimit(
            tenant_id=test_tenant,
            currency_code="USD",
            max_daily_budget=100000.0,
        )
        session.add(currency_limit)
        session.commit()

    yield "USD"

    # Cleanup
    with get_db_session() as session:
        stmt = select(CurrencyLimit).filter_by(tenant_id=test_tenant, currency_code="USD")
        limit = session.scalars(stmt).first()
        if limit:
            session.delete(limit)
            session.commit()


@pytest.fixture
def test_property_tag(integration_db, test_tenant):
    """Create required PropertyTag for property_tags array references.

    Per CLAUDE.md "Database Initialization Dependencies":
    Products with property_tags=["all_inventory"] require PropertyTag record.
    """
    with get_db_session() as session:
        property_tag = PropertyTag(
            tenant_id=test_tenant,
            tag_id="all_inventory",
            name="All Inventory",
            description="All available inventory",
        )
        session.add(property_tag)
        session.commit()

    yield "all_inventory"

    # Cleanup
    with get_db_session() as session:
        stmt = select(PropertyTag).filter_by(tenant_id=test_tenant, tag_id="all_inventory")
        tag = session.scalars(stmt).first()
        if tag:
            session.delete(tag)
            session.commit()


@pytest.fixture
def test_principal(integration_db, test_tenant):
    """Create test principal."""
    principal_id = "test_advertiser"
    with get_db_session() as session:
        principal = Principal(
            tenant_id=test_tenant,
            principal_id=principal_id,
            name="Test Advertiser",
            access_token="test_token_12345",
            platform_mappings={"mock": {"advertiser_id": "test_adv"}},
        )
        session.add(principal)
        session.commit()

    yield principal_id

    # Cleanup
    with get_db_session() as session:
        stmt = select(Principal).filter_by(tenant_id=test_tenant, principal_id=principal_id)
        principal = session.scalars(stmt).first()
        if principal:
            session.delete(principal)
            session.commit()


@pytest.mark.requires_db
class TestFormatConversionApproval:
    """Test format conversion during media buy approval execution."""

    def test_valid_format_reference_dict_conversion(
        self, test_tenant, test_principal, test_currency_limit, test_property_tag
    ):
        """✅ Valid FormatReference dict (with format_id) converts to FormatId successfully."""
        product_id = "prod_format_ref"
        media_buy_id = "mb_format_ref"

        with get_db_session() as session:
            # Create product with FormatReference-style dict (has format_id field)
            product = Product(
                tenant_id=test_tenant,
                product_id=product_id,
                name="Format Reference Product",
                description="Product with FormatReference format",
                formats=[
                    {
                        "agent_url": "https://creatives.example.com",
                        "format_id": "display_300x250",  # Legacy field name
                    }
                ],
                targeting_template={},
                delivery_type="guaranteed",
                property_tags=["all_inventory"],
            )
            session.add(product)

            # Add pricing option
            pricing = PricingOption(
                tenant_id=test_tenant,
                product_id=product_id,
                pricing_model="CPM",
                rate=Decimal("10.00"),
                currency="USD",
                is_fixed=True,
            )
            session.add(pricing)

            # Create media buy
            now = datetime.now(UTC)
            media_buy = MediaBuy(
                tenant_id=test_tenant,
                media_buy_id=media_buy_id,
                principal_id=test_principal,
                order_name="Format Ref Test Order",
                advertiser_name="Test Advertiser",
                budget=1000.0,
                start_date=(now + timedelta(days=1)).date(),
                end_date=(now + timedelta(days=7)).date(),
                start_time=now + timedelta(days=1),
                end_time=now + timedelta(days=7),
                status="pending_approval",
                raw_request={
                    "packages": [
                        {
                            "package_id": "pkg_1",
                            "product_id": product_id,
                            "budget": 1000.0,
                        }
                    ]
                },
            )
            session.add(media_buy)
            session.commit()

        # Execute approval
        success, message = execute_approved_media_buy(media_buy_id, test_tenant)

        assert success, f"Approval should succeed: {message}"
        assert "successfully" in message.lower()

        # Cleanup
        with get_db_session() as session:
            stmt_mb = select(MediaBuy).filter_by(media_buy_id=media_buy_id)
            media_buy = session.scalars(stmt_mb).first()
            if media_buy:
                session.delete(media_buy)

            stmt_prod = select(Product).filter_by(product_id=product_id)
            product = session.scalars(stmt_prod).first()
            if product:
                session.delete(product)

            session.commit()

    def test_invalid_format_missing_agent_url(
        self, test_tenant, test_principal, test_currency_limit, test_property_tag
    ):
        """❌ FormatReference dict missing agent_url should fail validation."""
        product_id = "prod_no_agent_url"
        media_buy_id = "mb_no_agent_url"

        with get_db_session() as session:
            # Create product with invalid format (no agent_url)
            product = Product(
                tenant_id=test_tenant,
                product_id=product_id,
                name="Invalid Format Product",
                description="Product with missing agent_url",
                formats=[
                    {
                        "format_id": "display_300x250",
                        # Missing agent_url - should fail
                    }
                ],
                targeting_template={},
                delivery_type="guaranteed",
                property_tags=["all_inventory"],
            )
            session.add(product)

            # Add pricing option
            pricing = PricingOption(
                tenant_id=test_tenant,
                product_id=product_id,
                pricing_model="CPM",
                rate=Decimal("10.00"),
                currency="USD",
                is_fixed=True,
            )
            session.add(pricing)

            # Create media buy
            now = datetime.now(UTC)
            media_buy = MediaBuy(
                tenant_id=test_tenant,
                media_buy_id=media_buy_id,
                principal_id=test_principal,
                order_name="Invalid Format Order",
                advertiser_name="Test Advertiser",
                budget=1000.0,
                start_date=(now + timedelta(days=1)).date(),
                end_date=(now + timedelta(days=7)).date(),
                start_time=now + timedelta(days=1),
                end_time=now + timedelta(days=7),
                status="pending_approval",
                raw_request={
                    "packages": [
                        {
                            "package_id": "pkg_1",
                            "product_id": product_id,
                            "budget": 1000.0,
                        }
                    ]
                },
            )
            session.add(media_buy)
            session.commit()

        # Execute approval - should fail
        success, message = execute_approved_media_buy(media_buy_id, test_tenant)

        assert not success, "Approval should fail with missing agent_url"
        assert "agent_url" in message.lower()
        assert "format validation failed" in message.lower()

        # Cleanup
        with get_db_session() as session:
            stmt_mb = select(MediaBuy).filter_by(media_buy_id=media_buy_id)
            media_buy = session.scalars(stmt_mb).first()
            if media_buy:
                session.delete(media_buy)

            stmt_prod = select(Product).filter_by(product_id=product_id)
            product = session.scalars(stmt_prod).first()
            if product:
                session.delete(product)

            session.commit()

    def test_invalid_format_empty_agent_url(self, test_tenant, test_principal, test_currency_limit, test_property_tag):
        """❌ FormatReference dict with empty agent_url should fail validation."""
        product_id = "prod_empty_agent_url"
        media_buy_id = "mb_empty_agent_url"

        with get_db_session() as session:
            # Create product with empty agent_url
            product = Product(
                tenant_id=test_tenant,
                product_id=product_id,
                name="Empty Agent URL Product",
                description="Product with empty agent_url",
                formats=[
                    {
                        "agent_url": "",  # Empty string - should fail
                        "format_id": "display_300x250",
                    }
                ],
                targeting_template={},
                delivery_type="guaranteed",
                property_tags=["all_inventory"],
            )
            session.add(product)

            # Add pricing option
            pricing = PricingOption(
                tenant_id=test_tenant,
                product_id=product_id,
                pricing_model="CPM",
                rate=Decimal("10.00"),
                currency="USD",
                is_fixed=True,
            )
            session.add(pricing)

            # Create media buy
            now = datetime.now(UTC)
            media_buy = MediaBuy(
                tenant_id=test_tenant,
                media_buy_id=media_buy_id,
                principal_id=test_principal,
                order_name="Empty Agent URL Order",
                advertiser_name="Test Advertiser",
                budget=1000.0,
                start_date=(now + timedelta(days=1)).date(),
                end_date=(now + timedelta(days=7)).date(),
                start_time=now + timedelta(days=1),
                end_time=now + timedelta(days=7),
                status="pending_approval",
                raw_request={
                    "packages": [
                        {
                            "package_id": "pkg_1",
                            "product_id": product_id,
                            "budget": 1000.0,
                        }
                    ]
                },
            )
            session.add(media_buy)
            session.commit()

        # Execute approval - should fail
        success, message = execute_approved_media_buy(media_buy_id, test_tenant)

        assert not success, "Approval should fail with empty agent_url"
        assert "agent_url" in message.lower()

        # Cleanup
        with get_db_session() as session:
            stmt_mb = select(MediaBuy).filter_by(media_buy_id=media_buy_id)
            media_buy = session.scalars(stmt_mb).first()
            if media_buy:
                session.delete(media_buy)

            stmt_prod = select(Product).filter_by(product_id=product_id)
            product = session.scalars(stmt_prod).first()
            if product:
                session.delete(product)

            session.commit()

    def test_invalid_agent_url_not_http(self, test_tenant, test_principal, test_currency_limit, test_property_tag):
        """❌ FormatReference with non-HTTP(S) agent_url should fail validation."""
        product_id = "prod_invalid_url"
        media_buy_id = "mb_invalid_url"

        with get_db_session() as session:
            # Create product with invalid URL scheme
            product = Product(
                tenant_id=test_tenant,
                product_id=product_id,
                name="Invalid URL Product",
                description="Product with non-HTTP URL",
                formats=[
                    {
                        "agent_url": "ftp://creatives.example.com",  # FTP not allowed
                        "format_id": "display_300x250",
                    }
                ],
                targeting_template={},
                delivery_type="guaranteed",
                property_tags=["all_inventory"],
            )
            session.add(product)

            # Add pricing option
            pricing = PricingOption(
                tenant_id=test_tenant,
                product_id=product_id,
                pricing_model="CPM",
                rate=Decimal("10.00"),
                currency="USD",
                is_fixed=True,
            )
            session.add(pricing)

            # Create media buy
            now = datetime.now(UTC)
            media_buy = MediaBuy(
                tenant_id=test_tenant,
                media_buy_id=media_buy_id,
                principal_id=test_principal,
                order_name="Invalid URL Order",
                advertiser_name="Test Advertiser",
                budget=1000.0,
                start_date=(now + timedelta(days=1)).date(),
                end_date=(now + timedelta(days=7)).date(),
                start_time=now + timedelta(days=1),
                end_time=now + timedelta(days=7),
                status="pending_approval",
                raw_request={
                    "packages": [
                        {
                            "package_id": "pkg_1",
                            "product_id": product_id,
                            "budget": 1000.0,
                        }
                    ]
                },
            )
            session.add(media_buy)
            session.commit()

        # Execute approval - should fail
        success, message = execute_approved_media_buy(media_buy_id, test_tenant)

        assert not success, "Approval should fail with non-HTTP URL"
        assert "agent_url" in message.lower()
        assert "http" in message.lower()

        # Cleanup
        with get_db_session() as session:
            stmt_mb = select(MediaBuy).filter_by(media_buy_id=media_buy_id)
            media_buy = session.scalars(stmt_mb).first()
            if media_buy:
                session.delete(media_buy)

            stmt_prod = select(Product).filter_by(product_id=product_id)
            product = session.scalars(stmt_prod).first()
            if product:
                session.delete(product)

            session.commit()

    def test_invalid_format_missing_format_id(
        self, test_tenant, test_principal, test_currency_limit, test_property_tag
    ):
        """❌ FormatReference dict missing format_id/id should fail validation."""
        product_id = "prod_no_format_id"
        media_buy_id = "mb_no_format_id"

        with get_db_session() as session:
            # Create product with missing format_id
            product = Product(
                tenant_id=test_tenant,
                product_id=product_id,
                name="No Format ID Product",
                description="Product with missing format_id",
                formats=[
                    {
                        "agent_url": "https://creatives.example.com",
                        # Missing format_id/id - should fail
                    }
                ],
                targeting_template={},
                delivery_type="guaranteed",
                property_tags=["all_inventory"],
            )
            session.add(product)

            # Add pricing option
            pricing = PricingOption(
                tenant_id=test_tenant,
                product_id=product_id,
                pricing_model="CPM",
                rate=Decimal("10.00"),
                currency="USD",
                is_fixed=True,
            )
            session.add(pricing)

            # Create media buy
            now = datetime.now(UTC)
            media_buy = MediaBuy(
                tenant_id=test_tenant,
                media_buy_id=media_buy_id,
                principal_id=test_principal,
                order_name="No Format ID Order",
                advertiser_name="Test Advertiser",
                budget=1000.0,
                start_date=(now + timedelta(days=1)).date(),
                end_date=(now + timedelta(days=7)).date(),
                start_time=now + timedelta(days=1),
                end_time=now + timedelta(days=7),
                status="pending_approval",
                raw_request={
                    "packages": [
                        {
                            "package_id": "pkg_1",
                            "product_id": product_id,
                            "budget": 1000.0,
                        }
                    ]
                },
            )
            session.add(media_buy)
            session.commit()

        # Execute approval - should fail
        success, message = execute_approved_media_buy(media_buy_id, test_tenant)

        assert not success, "Approval should fail with missing format_id"
        assert "id" in message.lower()
        assert "format validation failed" in message.lower()

        # Cleanup
        with get_db_session() as session:
            stmt_mb = select(MediaBuy).filter_by(media_buy_id=media_buy_id)
            media_buy = session.scalars(stmt_mb).first()
            if media_buy:
                session.delete(media_buy)

            stmt_prod = select(Product).filter_by(product_id=product_id)
            product = session.scalars(stmt_prod).first()
            if product:
                session.delete(product)

            session.commit()

    def test_valid_format_id_dict_conversion(self, test_tenant, test_principal, test_currency_limit, test_property_tag):
        """✅ Valid FormatId dict (with 'id' key) converts successfully."""
        product_id = "prod_format_id"
        media_buy_id = "mb_format_id"

        with get_db_session() as session:
            # Create product with FormatId-style dict (has 'id' field, not 'format_id')
            product = Product(
                tenant_id=test_tenant,
                product_id=product_id,
                name="Format ID Product",
                description="Product with FormatId format",
                formats=[
                    {
                        "agent_url": "https://creatives.example.com",
                        "id": "display_728x90",  # New field name per AdCP spec
                    }
                ],
                targeting_template={},
                delivery_type="guaranteed",
                property_tags=["all_inventory"],
            )
            session.add(product)

            # Add pricing option
            pricing = PricingOption(
                tenant_id=test_tenant,
                product_id=product_id,
                pricing_model="CPM",
                rate=Decimal("15.00"),
                currency="USD",
                is_fixed=True,
            )
            session.add(pricing)

            # Create media buy
            now = datetime.now(UTC)
            media_buy = MediaBuy(
                tenant_id=test_tenant,
                media_buy_id=media_buy_id,
                principal_id=test_principal,
                order_name="Format ID Test Order",
                advertiser_name="Test Advertiser",
                budget=1500.0,
                start_date=(now + timedelta(days=1)).date(),
                end_date=(now + timedelta(days=7)).date(),
                start_time=now + timedelta(days=1),
                end_time=now + timedelta(days=7),
                status="pending_approval",
                raw_request={
                    "packages": [
                        {
                            "package_id": "pkg_1",
                            "product_id": product_id,
                            "budget": 1500.0,
                        }
                    ]
                },
            )
            session.add(media_buy)
            session.commit()

        # Execute approval
        success, message = execute_approved_media_buy(media_buy_id, test_tenant)

        assert success, f"Approval should succeed: {message}"
        assert "successfully" in message.lower()

        # Cleanup
        with get_db_session() as session:
            stmt_mb = select(MediaBuy).filter_by(media_buy_id=media_buy_id)
            media_buy = session.scalars(stmt_mb).first()
            if media_buy:
                session.delete(media_buy)

            stmt_prod = select(Product).filter_by(product_id=product_id)
            product = session.scalars(stmt_prod).first()
            if product:
                session.delete(product)

            session.commit()

    def test_invalid_dict_missing_id(self, test_tenant, test_principal, test_currency_limit, test_property_tag):
        """❌ Dict with neither 'id' nor 'format_id' should fail validation."""
        product_id = "prod_missing_both"
        media_buy_id = "mb_missing_both"

        with get_db_session() as session:
            # Create product with dict missing both id fields
            product = Product(
                tenant_id=test_tenant,
                product_id=product_id,
                name="Missing ID Product",
                description="Product with dict missing both id fields",
                formats=[
                    {
                        "agent_url": "https://creatives.example.com",
                        "name": "Display Ad",  # Wrong field - not id or format_id
                    }
                ],
                targeting_template={},
                delivery_type="guaranteed",
                property_tags=["all_inventory"],
            )
            session.add(product)

            # Add pricing option
            pricing = PricingOption(
                tenant_id=test_tenant,
                product_id=product_id,
                pricing_model="CPM",
                rate=Decimal("10.00"),
                currency="USD",
                is_fixed=True,
            )
            session.add(pricing)

            # Create media buy
            now = datetime.now(UTC)
            media_buy = MediaBuy(
                tenant_id=test_tenant,
                media_buy_id=media_buy_id,
                principal_id=test_principal,
                order_name="Missing Both IDs Order",
                advertiser_name="Test Advertiser",
                budget=1000.0,
                start_date=(now + timedelta(days=1)).date(),
                end_date=(now + timedelta(days=7)).date(),
                start_time=now + timedelta(days=1),
                end_time=now + timedelta(days=7),
                status="pending_approval",
                raw_request={
                    "packages": [
                        {
                            "package_id": "pkg_1",
                            "product_id": product_id,
                            "budget": 1000.0,
                        }
                    ]
                },
            )
            session.add(media_buy)
            session.commit()

        # Execute approval - should fail
        success, message = execute_approved_media_buy(media_buy_id, test_tenant)

        assert not success, "Approval should fail with missing id/format_id"
        assert "id" in message.lower()

        # Cleanup
        with get_db_session() as session:
            stmt_mb = select(MediaBuy).filter_by(media_buy_id=media_buy_id)
            media_buy = session.scalars(stmt_mb).first()
            if media_buy:
                session.delete(media_buy)

            stmt_prod = select(Product).filter_by(product_id=product_id)
            product = session.scalars(stmt_prod).first()
            if product:
                session.delete(product)

            session.commit()

    def test_empty_formats_list_fails(self, test_tenant, test_principal, test_currency_limit, test_property_tag):
        """❌ Product with empty formats list should fail validation."""
        product_id = "prod_empty_formats"
        media_buy_id = "mb_empty_formats"

        with get_db_session() as session:
            # Create product with empty formats list
            product = Product(
                tenant_id=test_tenant,
                product_id=product_id,
                name="Empty Formats Product",
                description="Product with no formats",
                formats=[],  # Empty list - should fail
                targeting_template={},
                delivery_type="guaranteed",
                property_tags=["all_inventory"],
            )
            session.add(product)

            # Add pricing option
            pricing = PricingOption(
                tenant_id=test_tenant,
                product_id=product_id,
                pricing_model="CPM",
                rate=Decimal("10.00"),
                currency="USD",
                is_fixed=True,
            )
            session.add(pricing)

            # Create media buy
            now = datetime.now(UTC)
            media_buy = MediaBuy(
                tenant_id=test_tenant,
                media_buy_id=media_buy_id,
                principal_id=test_principal,
                order_name="Empty Formats Order",
                advertiser_name="Test Advertiser",
                budget=1000.0,
                start_date=(now + timedelta(days=1)).date(),
                end_date=(now + timedelta(days=7)).date(),
                start_time=now + timedelta(days=1),
                end_time=now + timedelta(days=7),
                status="pending_approval",
                raw_request={
                    "packages": [
                        {
                            "package_id": "pkg_1",
                            "product_id": product_id,
                            "budget": 1000.0,
                        }
                    ]
                },
            )
            session.add(media_buy)
            session.commit()

        # Execute approval - should fail
        success, message = execute_approved_media_buy(media_buy_id, test_tenant)

        assert not success, "Approval should fail with empty formats"
        assert "no valid formats" in message.lower()

        # Cleanup
        with get_db_session() as session:
            stmt_mb = select(MediaBuy).filter_by(media_buy_id=media_buy_id)
            media_buy = session.scalars(stmt_mb).first()
            if media_buy:
                session.delete(media_buy)

            stmt_prod = select(Product).filter_by(product_id=product_id)
            product = session.scalars(stmt_prod).first()
            if product:
                session.delete(product)

            session.commit()

    def test_mixed_valid_format_types(self, test_tenant, test_principal, test_currency_limit, test_property_tag):
        """✅ Product with mixed valid format types (FormatRef, FormatId, dict) succeeds."""
        product_id = "prod_mixed_formats"
        media_buy_id = "mb_mixed_formats"

        with get_db_session() as session:
            # Create product with multiple format types
            product = Product(
                tenant_id=test_tenant,
                product_id=product_id,
                name="Mixed Formats Product",
                description="Product with different format styles",
                formats=[
                    # FormatReference style (legacy)
                    {
                        "agent_url": "https://creatives.example.com",
                        "format_id": "display_300x250",
                    },
                    # FormatId style (new)
                    {
                        "agent_url": "https://creatives.example.com",
                        "id": "display_728x90",
                    },
                    # Another FormatId style
                    {
                        "agent_url": "https://creatives.example.com",
                        "id": "display_160x600",
                    },
                ],
                targeting_template={},
                delivery_type="guaranteed",
                property_tags=["all_inventory"],
            )
            session.add(product)

            # Add pricing option
            pricing = PricingOption(
                tenant_id=test_tenant,
                product_id=product_id,
                pricing_model="CPM",
                rate=Decimal("20.00"),
                currency="USD",
                is_fixed=True,
            )
            session.add(pricing)

            # Create media buy
            now = datetime.now(UTC)
            media_buy = MediaBuy(
                tenant_id=test_tenant,
                media_buy_id=media_buy_id,
                principal_id=test_principal,
                order_name="Mixed Formats Order",
                advertiser_name="Test Advertiser",
                budget=2000.0,
                start_date=(now + timedelta(days=1)).date(),
                end_date=(now + timedelta(days=7)).date(),
                start_time=now + timedelta(days=1),
                end_time=now + timedelta(days=7),
                status="pending_approval",
                raw_request={
                    "packages": [
                        {
                            "package_id": "pkg_1",
                            "product_id": product_id,
                            "budget": 2000.0,
                        }
                    ]
                },
            )
            session.add(media_buy)
            session.commit()

        # Execute approval - should succeed
        success, message = execute_approved_media_buy(media_buy_id, test_tenant)

        assert success, f"Approval should succeed with mixed formats: {message}"
        assert "successfully" in message.lower()

        # Cleanup
        with get_db_session() as session:
            stmt_mb = select(MediaBuy).filter_by(media_buy_id=media_buy_id)
            media_buy = session.scalars(stmt_mb).first()
            if media_buy:
                session.delete(media_buy)

            stmt_prod = select(Product).filter_by(product_id=product_id)
            product = session.scalars(stmt_prod).first()
            if product:
                session.delete(product)

            session.commit()

    def test_invalid_format_unknown_type(self, test_tenant, test_principal, test_currency_limit, test_property_tag):
        """❌ Format with unknown type (string, int) should fail validation."""
        product_id = "prod_invalid_type"
        media_buy_id = "mb_invalid_type"

        with get_db_session() as session:
            # Create product with invalid format type (string instead of dict)
            product = Product(
                tenant_id=test_tenant,
                product_id=product_id,
                name="Invalid Type Product",
                description="Product with string format (should be dict)",
                formats=["display_300x250"],  # String instead of dict - should fail
                targeting_template={},
                delivery_type="guaranteed",
                property_tags=["all_inventory"],
            )
            session.add(product)

            # Add pricing option
            pricing = PricingOption(
                tenant_id=test_tenant,
                product_id=product_id,
                pricing_model="CPM",
                rate=Decimal("10.00"),
                currency="USD",
                is_fixed=True,
            )
            session.add(pricing)

            # Create media buy
            now = datetime.now(UTC)
            media_buy = MediaBuy(
                tenant_id=test_tenant,
                media_buy_id=media_buy_id,
                principal_id=test_principal,
                order_name="Invalid Type Order",
                advertiser_name="Test Advertiser",
                budget=1000.0,
                start_date=(now + timedelta(days=1)).date(),
                end_date=(now + timedelta(days=7)).date(),
                start_time=now + timedelta(days=1),
                end_time=now + timedelta(days=7),
                status="pending_approval",
                raw_request={
                    "packages": [
                        {
                            "package_id": "pkg_1",
                            "product_id": product_id,
                            "budget": 1000.0,
                        }
                    ]
                },
            )
            session.add(media_buy)
            session.commit()

        # Execute approval - should fail
        success, message = execute_approved_media_buy(media_buy_id, test_tenant)

        assert not success, "Approval should fail with unknown format type"
        assert "unknown format type" in message.lower() or "format validation failed" in message.lower()

        # Cleanup
        with get_db_session() as session:
            stmt_mb = select(MediaBuy).filter_by(media_buy_id=media_buy_id)
            media_buy = session.scalars(stmt_mb).first()
            if media_buy:
                session.delete(media_buy)

            stmt_prod = select(Product).filter_by(product_id=product_id)
            product = session.scalars(stmt_prod).first()
            if product:
                session.delete(product)

            session.commit()
