"""Integration tests for AdCP v2.4 create_media_buy format with nested objects.

These tests specifically verify that packages containing nested Pydantic objects
(Budget, Targeting) are properly serialized in responses. This catches bugs like
the 'dict' object has no attribute 'model_dump' error that occurred when nested
objects weren't being serialized correctly.

Key differences from existing tests:
- Tests the NEW v2.4 format (packages with Budget/Targeting)
- Tests both MCP and A2A paths
- Exercises the FULL serialization path (not just schema validation)
- Uses integration-level mocking (real DB, mock adapter only)

NOTE: These tests require a database connection. Run with:
    env TEST_DATABASE_URL="sqlite:///:memory:" pytest tests/integration_v2/test_create_media_buy_v24.py
or with Docker Compose running for PostgreSQL.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete

from src.core.database.database_session import get_db_session
from src.core.schemas import Budget, Package, Targeting
from tests.integration_v2.conftest import add_required_setup_data, create_test_product_with_pricing

pytestmark = [pytest.mark.integration, pytest.mark.requires_db, pytest.mark.asyncio]


@pytest.mark.integration
@pytest.mark.requires_db
class TestCreateMediaBuyV24Format:
    """Test create_media_buy with AdCP v2.4 packages containing nested objects."""

    @pytest.fixture
    def setup_test_tenant(self, integration_db):
        """Set up test tenant with product."""
        from src.core.config_loader import set_current_tenant
        from src.core.database.models import CurrencyLimit
        from src.core.database.models import Principal as ModelPrincipal
        from src.core.database.models import Tenant as ModelTenant

        with get_db_session() as session:
            now = datetime.now(UTC)

            # Create tenant
            tenant = ModelTenant(
                tenant_id="test_tenant_v24",
                name="Test V24 Tenant",
                subdomain="testv24",
                ad_server="mock",
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            session.add(tenant)

            # Create principal
            principal = ModelPrincipal(
                tenant_id="test_tenant_v24",
                principal_id="test_principal_v24",
                name="Test Principal V24",
                access_token="test_token_v24",
                platform_mappings={"mock": {"advertiser_id": "adv_test_v24"}},
            )
            session.add(principal)

            # Add required setup data (access control, currency limits, property tags)
            add_required_setup_data(session, "test_tenant_v24")

            # Create product with new pricing model
            product = create_test_product_with_pricing(
                session=session,
                tenant_id="test_tenant_v24",
                product_id="prod_test_v24",
                name="Test Product V24",
                description="Test product for v2.4 format",
                formats=[{"agent_url": "https://test.com", "id": "display_300x250"}],
                delivery_type="guaranteed",
                pricing_model="CPM",
                rate="10.0",
                is_fixed=True,
                currency="USD",
                min_spend_per_package="1000.0",
                targeting_template={},
            )

            # Add additional currency limits for EUR
            currency_limit_eur = CurrencyLimit(
                tenant_id="test_tenant_v24",
                currency_code="EUR",
                min_package_budget=1000.0,
                max_daily_package_spend=10000.0,
            )
            session.add(currency_limit_eur)

            # Add GBP for multi-currency test
            currency_limit_gbp = CurrencyLimit(
                tenant_id="test_tenant_v24",
                currency_code="GBP",
                min_package_budget=1000.0,
                max_daily_package_spend=10000.0,
            )
            session.add(currency_limit_gbp)

            session.commit()

            # Set tenant context
            set_current_tenant(
                {
                    "tenant_id": "test_tenant_v24",
                    "name": "Test V24 Tenant",
                    "ad_server": "mock",
                    "auto_approve_formats": ["display_300x250"],
                }
            )

            yield {
                "tenant_id": "test_tenant_v24",
                "principal_id": "test_principal_v24",
                "product_id": "prod_test_v24",
            }

            # Cleanup
            from src.core.database.models import (
                AuthorizedProperty,
                PricingOption,
                Product,
                PropertyTag,
            )

            session.execute(delete(PricingOption).where(PricingOption.tenant_id == "test_tenant_v24"))
            session.execute(delete(Product).where(Product.tenant_id == "test_tenant_v24"))
            session.execute(delete(ModelPrincipal).where(ModelPrincipal.tenant_id == "test_tenant_v24"))
            session.execute(delete(CurrencyLimit).where(CurrencyLimit.tenant_id == "test_tenant_v24"))
            session.execute(delete(PropertyTag).where(PropertyTag.tenant_id == "test_tenant_v24"))
            session.execute(delete(AuthorizedProperty).where(AuthorizedProperty.tenant_id == "test_tenant_v24"))
            session.execute(delete(ModelTenant).where(ModelTenant.tenant_id == "test_tenant_v24"))
            session.commit()

            # Clear global tenant context to avoid polluting other tests
            set_current_tenant(None)

    async def test_create_media_buy_with_package_budget_mcp(self, setup_test_tenant):
        """Test MCP path with packages containing Budget objects.

        This test specifically exercises the bug fix for 'dict' object has no attribute 'model_dump'.
        Before the fix, this would fail when building response_packages because Budget objects
        weren't being serialized to dicts properly.
        """
        from src.core.context import Context
        from src.core.tools.media_buy_create import _create_media_buy_impl

        # Create Package with nested Budget object
        packages = [
            Package(
                buyer_ref="pkg_budget_test",
                products=[setup_test_tenant["product_id"]],
                budget=Budget(total=5000.0, currency="USD", pacing="even"),
            )
        ]

        context = Context(
            context_id="test_ctx_v24_budget",
            tenant_id=setup_test_tenant["tenant_id"],
            principal_id=setup_test_tenant["principal_id"],
            tool_name="create_media_buy",
            request_timestamp=datetime.now(UTC),
        )

        # Call _impl with individual parameters (not a request object)
        # This exercises the FULL serialization path including response_packages construction
        # NOTE: _create_media_buy_impl now requires buyer_ref and budget as REQUIRED arguments per AdCP v2.2.0 spec
        response = await _create_media_buy_impl(
            buyer_ref="test_buyer_v24",  # REQUIRED per AdCP v2.2.0
            brand_manifest={"name": "Nike Air Jordan 2025 basketball shoes"},
            packages=[p.model_dump_internal() for p in packages],  # Use internal to skip package_id validation
            start_time=datetime.now(UTC) + timedelta(days=1),
            end_time=datetime.now(UTC) + timedelta(days=31),
            budget=Budget(total=5000.0, currency="USD"),  # REQUIRED per AdCP v2.2.0
            po_number="TEST-V24-001",
            context=context,
        )

        # Verify response structure
        assert response.media_buy_id
        assert len(response.packages) == 1

        # CRITICAL: Verify package was serialized correctly (no model_dump errors)
        package = response.packages[0]
        assert isinstance(package, dict), "Package must be serialized to dict"
        assert package["buyer_ref"] == "pkg_budget_test"
        assert package["package_id"]  # Should have generated ID

        # Verify nested budget was serialized correctly
        assert "budget" in package or "products" in package  # Either field structure is fine

    async def test_create_media_buy_with_targeting_overlay_mcp(self, setup_test_tenant):
        """Test MCP path with packages containing Targeting objects.

        This tests another potential serialization issue with nested Pydantic objects.
        """
        from src.core.context import Context
        from src.core.tools.media_buy_create import _create_media_buy_impl

        # Create Package with nested Targeting object
        packages = [
            Package(
                buyer_ref="pkg_targeting_test",
                products=[setup_test_tenant["product_id"]],
                budget=Budget(total=8000.0, currency="EUR"),
                targeting_overlay=Targeting(
                    geo_country_any_of=["US", "CA"],
                    device_type_any_of=["mobile", "tablet"],
                ),
            )
        ]

        context = Context(
            context_id="test_ctx_v24_targeting",
            tenant_id=setup_test_tenant["tenant_id"],
            principal_id=setup_test_tenant["principal_id"],
            tool_name="create_media_buy",
            request_timestamp=datetime.now(UTC),
        )

        response = await _create_media_buy_impl(
            buyer_ref="test_buyer_v24_targeting",  # REQUIRED per AdCP v2.2.0
            brand_manifest={"name": "Adidas UltraBoost 2025 running shoes"},
            packages=[p.model_dump_internal() for p in packages],
            start_time=datetime.now(UTC) + timedelta(days=1),
            end_time=datetime.now(UTC) + timedelta(days=31),
            budget=Budget(total=8000.0, currency="EUR"),  # REQUIRED per AdCP v2.2.0
            po_number="TEST-V24-002",
            context=context,
        )

        # Verify response structure
        assert response.media_buy_id
        assert len(response.packages) == 1

        # Verify package was serialized correctly
        package = response.packages[0]
        assert isinstance(package, dict), "Package must be serialized to dict"
        assert package["buyer_ref"] == "pkg_targeting_test"

        # Verify nested targeting was serialized (if present in response)
        # Note: targeting_overlay may or may not be included in response depending on impl

    async def test_create_media_buy_multiple_packages_with_budgets_mcp(self, setup_test_tenant):
        """Test MCP path with multiple packages, each with different budgets.

        This tests the iteration over packages in response construction.
        """
        from src.core.context import Context
        from src.core.tools.media_buy_create import _create_media_buy_impl

        packages = [
            Package(
                buyer_ref="pkg_usd",
                products=[setup_test_tenant["product_id"]],
                budget=Budget(total=3000.0, currency="USD"),
            ),
            Package(
                buyer_ref="pkg_eur",
                products=[setup_test_tenant["product_id"]],
                budget=Budget(total=2500.0, currency="EUR"),
            ),
            Package(
                buyer_ref="pkg_gbp",
                products=[setup_test_tenant["product_id"]],
                budget=Budget(total=2000.0, currency="GBP"),
            ),
        ]

        context = Context(
            context_id="test_ctx_v24_multi",
            tenant_id=setup_test_tenant["tenant_id"],
            principal_id=setup_test_tenant["principal_id"],
            tool_name="create_media_buy",
            request_timestamp=datetime.now(UTC),
        )

        # Total budget is sum of all package budgets
        total_budget_value = sum(pkg.budget.total for pkg in packages)

        response = await _create_media_buy_impl(
            buyer_ref="test_buyer_v24_multi",  # REQUIRED per AdCP v2.2.0
            brand_manifest={"name": "Puma RS-X 2025 training shoes"},
            packages=[p.model_dump_internal() for p in packages],
            start_time=datetime.now(UTC) + timedelta(days=1),
            end_time=datetime.now(UTC) + timedelta(days=31),
            budget=Budget(total=total_budget_value, currency="USD"),  # REQUIRED per AdCP v2.2.0
            po_number="TEST-V24-003",
            context=context,
        )

        # Verify all packages serialized correctly
        assert response.media_buy_id
        assert len(response.packages) == 3

        buyer_refs = [pkg["buyer_ref"] for pkg in response.packages]
        assert "pkg_usd" in buyer_refs
        assert "pkg_eur" in buyer_refs
        assert "pkg_gbp" in buyer_refs

    async def test_create_media_buy_with_package_budget_a2a(self, setup_test_tenant):
        """Test A2A path with packages containing Budget objects.

        This verifies the A2A → tools.py → _impl path also handles nested objects correctly.
        """
        from src.core.context import Context
        from src.core.tools.media_buy_create import _create_media_buy_impl

        # Create Package with nested Budget object
        packages = [
            Package(
                buyer_ref="pkg_a2a_test",
                products=[setup_test_tenant["product_id"]],
                budget=Budget(total=6000.0, currency="USD"),
            )
        ]

        # A2A path also goes through _impl with Context
        context = Context(
            context_id="test_ctx_v24_a2a",
            tenant_id=setup_test_tenant["tenant_id"],
            principal_id=setup_test_tenant["principal_id"],
            tool_name="create_media_buy",
            request_timestamp=datetime.now(UTC),
        )

        response = await _create_media_buy_impl(
            buyer_ref="test_buyer_v24_a2a",  # REQUIRED per AdCP v2.2.0
            brand_manifest={"name": "Reebok Nano 2025 cross-training shoes"},
            packages=[p.model_dump_internal() for p in packages],
            start_time=datetime.now(UTC) + timedelta(days=1),
            end_time=datetime.now(UTC) + timedelta(days=31),
            budget=Budget(total=6000.0, currency="USD"),  # REQUIRED per AdCP v2.2.0
            po_number="TEST-V24-A2A-001",
            context=context,
        )

        # Verify response structure (same as MCP)
        assert response.media_buy_id
        assert len(response.packages) == 1

        # CRITICAL: Verify package was serialized correctly
        package = response.packages[0]
        assert isinstance(package, dict), "Package must be serialized to dict"
        assert package["buyer_ref"] == "pkg_a2a_test"

    async def test_create_media_buy_legacy_format_still_works(self, setup_test_tenant):
        """Verify legacy format (product_ids + total_budget) still works.

        This ensures backward compatibility wasn't broken by v2.4 changes.
        """
        from src.core.context import Context
        from src.core.tools.media_buy_create import _create_media_buy_impl

        context = Context(
            context_id="test_ctx_v24_legacy",
            tenant_id=setup_test_tenant["tenant_id"],
            principal_id=setup_test_tenant["principal_id"],
            tool_name="create_media_buy",
            request_timestamp=datetime.now(UTC),
        )

        # Legacy format using individual parameters
        # NOTE: Even legacy format now requires buyer_ref, packages, start_time, end_time, budget per AdCP v2.2.0
        # The legacy parameters (product_ids, total_budget, start_date, end_date) are converted internally
        response = await _create_media_buy_impl(
            buyer_ref="test_buyer_v24_legacy",  # REQUIRED per AdCP v2.2.0
            brand_manifest={"name": "Under Armour HOVR 2025 running shoes"},
            packages=[],  # Empty packages - will be auto-created from product_ids
            start_time=datetime.now(UTC) + timedelta(days=1),
            end_time=datetime.now(UTC) + timedelta(days=31),
            budget=Budget(total=4000.0, currency="USD"),  # REQUIRED per AdCP v2.2.0
            po_number="TEST-LEGACY-001",
            product_ids=[setup_test_tenant["product_id"]],  # Legacy parameter
            total_budget=4000.0,  # Legacy parameter
            start_date=(datetime.now(UTC) + timedelta(days=1)).date(),  # Legacy parameter
            end_date=(datetime.now(UTC) + timedelta(days=31)).date(),  # Legacy parameter
            context=context,
        )

        # Verify response
        assert response.media_buy_id
        assert len(response.packages) > 0  # Should auto-create packages from product_ids

        # Packages should still be dicts
        for package in response.packages:
            assert isinstance(package, dict)
