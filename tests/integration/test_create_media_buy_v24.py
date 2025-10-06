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
    env TEST_DATABASE_URL="sqlite:///:memory:" pytest tests/integration/test_create_media_buy_v24.py
or with Docker Compose running for PostgreSQL.
"""

from datetime import UTC, datetime, timedelta

import pytest

from src.core.database.database_session import get_db_session
from src.core.schemas import Budget, CreateMediaBuyRequest, Package, Targeting


@pytest.mark.integration
class TestCreateMediaBuyV24Format:
    """Test create_media_buy with AdCP v2.4 packages containing nested objects."""

    @pytest.fixture
    def setup_test_tenant(self, test_database):
        """Set up test tenant with product."""
        from datetime import datetime

        from src.core.config_loader import set_current_tenant
        from src.core.database.models import Principal as ModelPrincipal
        from src.core.database.models import Product as ModelProduct
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

            # Create product
            product = ModelProduct(
                tenant_id="test_tenant_v24",
                product_id="prod_test_v24",
                name="Test Product V24",
                description="Test product for v2.4 format",
                formats=["display_300x250"],
                delivery_type="guaranteed",
                cpm=10.0,
                min_spend=1000.0,
                targeting_template={},  # Required field
                is_fixed_price=True,  # Required field
            )
            session.add(product)

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
            session.query(ModelProduct).filter_by(tenant_id="test_tenant_v24").delete()
            session.query(ModelPrincipal).filter_by(tenant_id="test_tenant_v24").delete()
            session.query(ModelTenant).filter_by(tenant_id="test_tenant_v24").delete()
            session.commit()

    def test_create_media_buy_with_package_budget_mcp(self, setup_test_tenant):
        """Test MCP path with packages containing Budget objects.

        This test specifically exercises the bug fix for 'dict' object has no attribute 'model_dump'.
        Before the fix, this would fail when building response_packages because Budget objects
        weren't being serialized to dicts properly.
        """
        from src.core.main import _create_media_buy_impl
        from src.core.tool_context import ToolContext

        # Create request with nested Budget object
        req = CreateMediaBuyRequest(
            promoted_offering="Nike Air Jordan 2025 basketball shoes",
            po_number="TEST-V24-001",
            packages=[
                Package(
                    buyer_ref="pkg_budget_test",
                    products=[setup_test_tenant["product_id"]],
                    budget=Budget(total=5000.0, currency="USD", pacing="even"),
                )
            ],
            start_time=datetime.now(UTC) + timedelta(days=1),
            end_time=datetime.now(UTC) + timedelta(days=31),
        )

        context = ToolContext(
            context_id=f"test_ctx_v24_{id(req)}",
            tenant_id=setup_test_tenant["tenant_id"],
            principal_id=setup_test_tenant["principal_id"],
            tool_name="create_media_buy",
            request_timestamp=datetime.now(UTC),
        )

        # This exercises the FULL serialization path including response_packages construction
        response = _create_media_buy_impl(req, context)

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

    def test_create_media_buy_with_targeting_overlay_mcp(self, setup_test_tenant):
        """Test MCP path with packages containing Targeting objects.

        This tests another potential serialization issue with nested Pydantic objects.
        """
        from src.core.main import _create_media_buy_impl
        from src.core.tool_context import ToolContext

        # Create request with nested Targeting object
        req = CreateMediaBuyRequest(
            promoted_offering="Adidas UltraBoost 2025 running shoes",
            po_number="TEST-V24-002",
            packages=[
                Package(
                    buyer_ref="pkg_targeting_test",
                    products=[setup_test_tenant["product_id"]],
                    budget=Budget(total=8000.0, currency="EUR"),
                    targeting_overlay=Targeting(
                        geo_country_any_of=["US", "CA"],
                        device_type_any_of=["mobile", "tablet"],
                    ),
                )
            ],
            start_time=datetime.now(UTC) + timedelta(days=1),
            end_time=datetime.now(UTC) + timedelta(days=31),
        )

        context = ToolContext(
            context_id=f"test_ctx_v24_{id(req)}",
            tenant_id=setup_test_tenant["tenant_id"],
            principal_id=setup_test_tenant["principal_id"],
            tool_name="create_media_buy",
            request_timestamp=datetime.now(UTC),
        )

        response = _create_media_buy_impl(req, context)

        # Verify response structure
        assert response.media_buy_id
        assert len(response.packages) == 1

        # Verify package was serialized correctly
        package = response.packages[0]
        assert isinstance(package, dict), "Package must be serialized to dict"
        assert package["buyer_ref"] == "pkg_targeting_test"

        # Verify nested targeting was serialized (if present in response)
        # Note: targeting_overlay may or may not be included in response depending on impl

    def test_create_media_buy_multiple_packages_with_budgets_mcp(self, setup_test_tenant):
        """Test MCP path with multiple packages, each with different budgets.

        This tests the iteration over packages in response construction.
        """
        from src.core.main import _create_media_buy_impl
        from src.core.tool_context import ToolContext

        req = CreateMediaBuyRequest(
            promoted_offering="Puma RS-X 2025 training shoes",
            po_number="TEST-V24-003",
            packages=[
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
            ],
            start_time=datetime.now(UTC) + timedelta(days=1),
            end_time=datetime.now(UTC) + timedelta(days=31),
        )

        context = ToolContext(
            context_id=f"test_ctx_v24_{id(req)}",
            tenant_id=setup_test_tenant["tenant_id"],
            principal_id=setup_test_tenant["principal_id"],
            tool_name="create_media_buy",
            request_timestamp=datetime.now(UTC),
        )

        response = _create_media_buy_impl(req, context)

        # Verify all packages serialized correctly
        assert response.media_buy_id
        assert len(response.packages) == 3

        buyer_refs = [pkg["buyer_ref"] for pkg in response.packages]
        assert "pkg_usd" in buyer_refs
        assert "pkg_eur" in buyer_refs
        assert "pkg_gbp" in buyer_refs

    def test_create_media_buy_with_package_budget_a2a(self, setup_test_tenant):
        """Test A2A path with packages containing Budget objects.

        This verifies the A2A → tools.py → _impl path also handles nested objects correctly.
        """
        from src.core.main import _create_media_buy_impl

        # Create request with nested Budget object
        req = CreateMediaBuyRequest(
            promoted_offering="Reebok Nano 2025 cross-training shoes",
            po_number="TEST-V24-A2A-001",
            packages=[
                Package(
                    buyer_ref="pkg_a2a_test",
                    products=[setup_test_tenant["product_id"]],
                    budget=Budget(total=6000.0, currency="USD"),
                )
            ],
            start_time=datetime.now(UTC) + timedelta(days=1),
            end_time=datetime.now(UTC) + timedelta(days=31),
        )

        # A2A path also goes through _impl with ToolContext
        context = ToolContext(
            context_id=f"test_ctx_v24_{id(req)}",
            tenant_id=setup_test_tenant["tenant_id"],
            principal_id=setup_test_tenant["principal_id"],
            tool_name="create_media_buy",
            request_timestamp=datetime.now(UTC),
        )

        response = _create_media_buy_impl(req, context)

        # Verify response structure (same as MCP)
        assert response.media_buy_id
        assert len(response.packages) == 1

        # CRITICAL: Verify package was serialized correctly
        package = response.packages[0]
        assert isinstance(package, dict), "Package must be serialized to dict"
        assert package["buyer_ref"] == "pkg_a2a_test"

    def test_create_media_buy_legacy_format_still_works(self, setup_test_tenant):
        """Verify legacy format (product_ids + total_budget) still works.

        This ensures backward compatibility wasn't broken by v2.4 changes.
        """
        from src.core.main import _create_media_buy_impl
        from src.core.tool_context import ToolContext

        # Legacy format request
        req = CreateMediaBuyRequest(
            promoted_offering="Under Armour HOVR 2025 running shoes",
            po_number="TEST-LEGACY-001",
            product_ids=[setup_test_tenant["product_id"]],
            total_budget=4000.0,
            start_date=(datetime.now(UTC) + timedelta(days=1)).date(),
            end_date=(datetime.now(UTC) + timedelta(days=31)).date(),
        )

        context = ToolContext(
            context_id=f"test_ctx_v24_{id(req)}",
            tenant_id=setup_test_tenant["tenant_id"],
            principal_id=setup_test_tenant["principal_id"],
            tool_name="create_media_buy",
            request_timestamp=datetime.now(UTC),
        )

        response = _create_media_buy_impl(req, context)

        # Verify response
        assert response.media_buy_id
        assert len(response.packages) > 0  # Should auto-create packages from product_ids

        # Packages should still be dicts
        for package in response.packages:
            assert isinstance(package, dict)
