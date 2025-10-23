#!/usr/bin/env python3
"""
Test validation for duplicate products in media buy packages.

Verifies that the system rejects media buy requests where the same product_id
appears in multiple packages, which would create ambiguous/duplicate line items.
"""

import logging
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete

from src.core.database.database_session import get_db_session
from src.core.database.models import CurrencyLimit, PropertyTag
from src.core.database.models import Principal as ModelPrincipal
from src.core.database.models import Product as ModelProduct
from src.core.database.models import Tenant as ModelTenant
from src.core.main import _create_media_buy_impl
from src.core.schemas import Budget, Package

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@pytest.mark.integration
@pytest.mark.requires_db
class TestDuplicateProductValidation:
    """Test that duplicate products in packages are rejected."""

    @pytest.fixture
    def test_tenant(self, integration_db):
        """Create test tenant with products."""
        from src.core.config_loader import set_current_tenant

        with get_db_session() as session:
            now = datetime.now(UTC)

            # Clean up existing test data
            session.execute(delete(ModelPrincipal).where(ModelPrincipal.tenant_id == "dup_prod_test"))
            session.execute(delete(ModelProduct).where(ModelProduct.tenant_id == "dup_prod_test"))
            session.execute(delete(PropertyTag).where(PropertyTag.tenant_id == "dup_prod_test"))
            session.execute(delete(CurrencyLimit).where(CurrencyLimit.tenant_id == "dup_prod_test"))
            session.execute(delete(ModelTenant).where(ModelTenant.tenant_id == "dup_prod_test"))
            session.commit()

            # Create tenant
            tenant = ModelTenant(
                tenant_id="dup_prod_test",
                name="Duplicate Product Test Tenant",
                subdomain="dupprod",
                ad_server="mock",
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            session.add(tenant)

            # Create property tag (required for products)
            property_tag = PropertyTag(
                tenant_id="dup_prod_test",
                tag_id="all_inventory",
                name="All Inventory",
                description="All available inventory",
                created_at=now,
            )
            session.add(property_tag)

            # Create two products
            product1 = ModelProduct(
                tenant_id="dup_prod_test",
                product_id="prod_dup_test_1",
                name="Test Product 1",
                description="First test product",
                formats=["display_300x250"],
                delivery_type="guaranteed",
                cpm=10.0,
                min_spend=1000.0,
                targeting_template={},
                is_fixed_price=True,
            )
            session.add(product1)

            product2 = ModelProduct(
                tenant_id="dup_prod_test",
                product_id="prod_dup_test_2",
                name="Test Product 2",
                description="Second test product",
                formats=["display_728x90"],
                delivery_type="guaranteed",
                cpm=15.0,
                min_spend=1000.0,
                targeting_template={},
                is_fixed_price=True,
            )
            session.add(product2)

            # Add currency limit
            currency_limit = CurrencyLimit(
                tenant_id="dup_prod_test",
                currency_code="USD",
                min_package_budget=1000.0,
                max_daily_package_spend=10000.0,
            )
            session.add(currency_limit)

            session.commit()

            # Set tenant context
            set_current_tenant(
                {
                    "tenant_id": "dup_prod_test",
                    "name": "Duplicate Product Test Tenant",
                    "subdomain": "dupprod",
                    "ad_server": "mock",
                }
            )

            yield {
                "tenant_id": "dup_prod_test",
                "name": "Duplicate Product Test Tenant",
                "subdomain": "dupprod",
                "ad_server": "mock",
            }

    @pytest.fixture
    def test_principal(self, test_tenant):
        """Create test principal."""
        with get_db_session() as session:
            principal = ModelPrincipal(
                tenant_id=test_tenant["tenant_id"],
                principal_id="dup_prod_principal",
                name="Duplicate Product Test Principal",
                access_token="dup_prod_token_123",
                advertiser_name="Duplicate Product Advertiser",
                is_active=True,
                platform_mappings={"mock": {"advertiser_id": "mock_adv_123"}},
            )
            session.add(principal)
            session.commit()

            yield {
                "principal_id": "dup_prod_principal",
                "access_token": "dup_prod_token_123",
                "name": "Duplicate Product Test Principal",
            }

    @pytest.mark.asyncio
    async def test_duplicate_product_in_packages_rejected(self, test_tenant, test_principal):
        """Test that duplicate product_ids in packages are rejected."""
        # Create packages with duplicate product_id
        packages = [
            Package(
                buyer_ref="pkg_1",
                product_id="prod_dup_test_1",
                budget=Budget(total=1000, currency="USD"),
            ),
            Package(
                buyer_ref="pkg_2",
                product_id="prod_dup_test_1",  # Same product as pkg_1
                budget=Budget(total=1500, currency="USD"),
            ),
        ]

        start_time = datetime.now(UTC)
        end_time = start_time + timedelta(days=7)

        # Should raise ValueError about duplicate products
        with pytest.raises(ValueError) as exc_info:
            await _create_media_buy_impl(
                buyer_ref="test_media_buy_duplicate",
                brand_manifest={"name": "Test Brand"},
                packages=packages,
                start_time=start_time,
                end_time=end_time,
                budget=Budget(total=2500, currency="USD"),
            )

        # Verify error message mentions duplicate products
        error_msg = str(exc_info.value)
        assert "duplicate" in error_msg.lower()
        assert "prod_dup_test_1" in error_msg

    @pytest.mark.asyncio
    async def test_different_products_in_packages_accepted(self, test_tenant, test_principal):
        """Test that different product_ids in packages are accepted."""
        # Create packages with different product_ids
        packages = [
            Package(
                buyer_ref="pkg_1",
                product_id="prod_dup_test_1",
                budget=Budget(total=1000, currency="USD"),
            ),
            Package(
                buyer_ref="pkg_2",
                product_id="prod_dup_test_2",  # Different product
                budget=Budget(total=1500, currency="USD"),
            ),
        ]

        start_time = datetime.now(UTC)
        end_time = start_time + timedelta(days=7)

        # Should succeed with different products
        response = await _create_media_buy_impl(
            buyer_ref="test_media_buy_different",
            brand_manifest={"name": "Test Brand"},
            packages=packages,
            start_time=start_time,
            end_time=end_time,
            budget=Budget(total=2500, currency="USD"),
        )

        # Verify response has both packages
        assert response.packages is not None
        assert len(response.packages) == 2
        assert response.packages[0].product_id == "prod_dup_test_1"
        assert response.packages[1].product_id == "prod_dup_test_2"

    @pytest.mark.asyncio
    async def test_multiple_duplicate_products_all_listed(self, test_tenant, test_principal):
        """Test that all duplicate product_ids are listed in error message."""
        # Create three products with two pairs of duplicates
        with get_db_session() as session:
            product3 = ModelProduct(
                tenant_id="dup_prod_test",
                product_id="prod_dup_test_3",
                name="Test Product 3",
                description="Third test product",
                formats=["display_160x600"],
                delivery_type="guaranteed",
                cpm=12.0,
                min_spend=1000.0,
                targeting_template={},
                is_fixed_price=True,
            )
            session.add(product3)
            session.commit()

        # Create packages with multiple duplicates
        packages = [
            Package(
                buyer_ref="pkg_1",
                product_id="prod_dup_test_1",
                budget=Budget(total=1000, currency="USD"),
            ),
            Package(
                buyer_ref="pkg_2",
                product_id="prod_dup_test_1",  # Duplicate of pkg_1
                budget=Budget(total=1500, currency="USD"),
            ),
            Package(
                buyer_ref="pkg_3",
                product_id="prod_dup_test_2",
                budget=Budget(total=2000, currency="USD"),
            ),
            Package(
                buyer_ref="pkg_4",
                product_id="prod_dup_test_2",  # Duplicate of pkg_3
                budget=Budget(total=1800, currency="USD"),
            ),
        ]

        start_time = datetime.now(UTC)
        end_time = start_time + timedelta(days=7)

        # Should raise ValueError listing both duplicate products
        with pytest.raises(ValueError) as exc_info:
            await _create_media_buy_impl(
                buyer_ref="test_media_buy_multiple_duplicates",
                brand_manifest={"name": "Test Brand"},
                packages=packages,
                start_time=start_time,
                end_time=end_time,
                budget=Budget(total=6300, currency="USD"),
            )

        # Verify both duplicate products are mentioned
        error_msg = str(exc_info.value)
        assert "prod_dup_test_1" in error_msg
        assert "prod_dup_test_2" in error_msg
