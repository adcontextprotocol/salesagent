"""Integration tests for signals agent workflow.

MIGRATED: Uses new pricing_options model instead of legacy Product pricing fields.
"""

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastmcp.server.context import Context
from sqlalchemy import select

from src.core.database.database_session import get_db_session
from src.core.database.models import Tenant
from src.core.main import get_products
from src.core.schema_adapters import GetProductsRequest
from src.core.schemas import Signal
from tests.fixtures.builders import create_test_tenant_with_principal
from tests.integration_v2.conftest import create_test_product_with_pricing


@pytest.mark.requires_server
@pytest.mark.asyncio
class TestSignalsAgentWorkflow:
    """Integration tests for signals agent workflow with real database."""

    @pytest.fixture
    async def tenant_with_signals_config(self) -> dict[str, Any]:
        """Create a test tenant with signals discovery configured."""
        tenant_data = await create_test_tenant_with_principal()
        tenant_id = tenant_data["tenant"]["tenant_id"]

        # Add signals configuration using real database
        signals_config = {
            "enabled": True,
            "upstream_url": "http://test-signals:8080/mcp/",
            "upstream_token": "test-token",
            "auth_header": "x-adcp-auth",
            "timeout": 30,
            "forward_promoted_offering": True,
            "fallback_to_database": True,
        }

        with get_db_session() as db_session:
            tenant = db_session.scalars(select(Tenant).filter_by(tenant_id=tenant_id)).first()
            if tenant:
                tenant.signals_agent_config = signals_config
                db_session.commit()

        return tenant_data

    @pytest.fixture
    async def tenant_without_signals_config(self) -> dict[str, Any]:
        """Create a test tenant without signals discovery."""
        return await create_test_tenant_with_principal()

    @pytest.fixture
    def mock_signals_response(self):
        """Mock signals response from upstream agent."""
        return [
            Signal(
                signal_id="sports_enthusiasts",
                name="Sports Enthusiasts",
                description="Users interested in sports content",
                type="audience",
                category="sports",
                reach=8.5,
                cpm_uplift=2.5,
            ),
            Signal(
                signal_id="automotive_intenders",
                name="Automotive Intenders",
                description="Users researching car purchases",
                type="audience",
                category="automotive",
                reach=4.2,
                cpm_uplift=3.0,
            ),
        ]

    @pytest.fixture
    def test_context_factory(self) -> Callable[[str, str], Mock]:
        """Factory for creating test contexts with authentication."""

        def _create_context(token="test-token-123", context_id="test-context-123"):
            context = Mock(spec=Context)
            context.meta = {"headers": {"x-adcp-auth": token, "x-context-id": context_id}}
            return context

        return _create_context

    async def test_get_products_without_signals_config(self, tenant_without_signals_config, test_context_factory):
        """Test get_products with tenant that has no signals configuration."""
        tenant_data = tenant_without_signals_config
        tenant_id = tenant_data["tenant"]["tenant_id"]
        principal_id = tenant_data["principal"].principal_id

        # Add test products to real database
        await self._add_test_products(tenant_id)

        request = GetProductsRequest(
            brief="sports car advertising campaign", brand_manifest={"name": "BMW M3 2025 sports sedan"}
        )
        context = test_context_factory()

        # Use single context patch with real tenant data
        with self._mock_auth_context(tenant_data):
            response = await get_products(request, context)

            # Should return database products only
            assert len(response.products) > 0

            # Verify no signals products
            for product in response.products:
                assert product.metadata.get("created_by") != "signals_discovery"

    async def test_get_products_with_signals_success(
        self, tenant_with_signals_config, test_context_factory, mock_signals_response
    ):
        """Test successful signals agent integration."""
        tenant_data = tenant_with_signals_config
        tenant_id = tenant_data["tenant"]["tenant_id"]

        await self._add_test_products(tenant_id)

        request = GetProductsRequest(
            brief="luxury sports car advertising for wealthy professionals",
            brand_manifest={"name": "Porsche 911 Turbo S 2025"},
        )
        context = test_context_factory()

        # Mock only external signals API call
        with patch("product_catalog_providers.signals.Client") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.__aenter__.return_value = mock_client
            mock_client.call_tool = AsyncMock(
                return_value={"signals": [signal.model_dump() for signal in mock_signals_response]}
            )

            with self._mock_auth_context(tenant_data):
                response = await get_products(request, context)

                # Should return both signals and database products
                assert len(response.products) > 0

                # Verify signals products are included
                signals_products = [p for p in response.products if p.metadata.get("created_by") == "signals_discovery"]
                assert len(signals_products) > 0

                # Verify signals call was made
                mock_client.call_tool.assert_called_once()

    async def test_get_products_signals_upstream_failure_fallback(
        self, tenant_with_signals_config, test_context_factory
    ):
        """Test fallback behavior when upstream signals agent fails."""
        tenant_data = tenant_with_signals_config
        tenant_id = tenant_data["tenant"]["tenant_id"]

        await self._add_test_products(tenant_id)

        request = GetProductsRequest(
            brief="test brief for failure scenario", brand_manifest={"name": "Test Product 2025"}
        )
        context = test_context_factory()

        # Mock upstream failure
        with patch("product_catalog_providers.signals.Client") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.__aenter__.return_value = mock_client
            mock_client.call_tool = AsyncMock(side_effect=Exception("Connection timeout"))

            with self._mock_auth_context(tenant_data):
                response = await get_products(request, context)

                # Should still return database products due to fallback
                assert len(response.products) > 0

                # All products should be from database (no signals products)
                signals_products = [p for p in response.products if p.metadata.get("created_by") == "signals_discovery"]
                assert len(signals_products) == 0

    async def test_get_products_no_brief_optimization(self, tenant_with_signals_config, test_context_factory):
        """Test that no signals call is made when brief is empty (optimization)."""
        tenant_data = tenant_with_signals_config
        tenant_id = tenant_data["tenant"]["tenant_id"]

        await self._add_test_products(tenant_id)

        request = GetProductsRequest(brief="", brand_manifest={"name": "Generic Product 2025"})
        context = test_context_factory()

        # Mock signals client to verify it's not called
        with patch("product_catalog_providers.signals.Client") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.__aenter__.return_value = mock_client
            mock_client.call_tool = AsyncMock()

            with self._mock_auth_context(tenant_data):
                response = await get_products(request, context)

                # Should return products but no signals call
                assert len(response.products) > 0

                # Verify upstream was NOT called (optimization)
                mock_client.call_tool.assert_not_called()

    def _mock_auth_context(self, tenant_data):
        """Helper to create authentication context patches."""
        return patch.multiple(
            "src.core.main",
            _get_principal_id_from_context=Mock(return_value=tenant_data["principal"].principal_id),
            get_current_tenant=Mock(return_value={"tenant_id": tenant_data["tenant"]["tenant_id"]}),
            get_principal_object=Mock(return_value=tenant_data["principal"]),
            PolicyCheckService=Mock(return_value=self._create_mock_policy_service()),
        )

    def _create_mock_policy_service(self):
        """Create a mock policy service that approves everything."""
        mock_policy = Mock()
        mock_policy.check_brief_compliance = AsyncMock(return_value=Mock(status="APPROVED", reason="", restrictions=[]))
        mock_policy.check_product_eligibility = Mock(return_value=(True, ""))
        return mock_policy

    async def _add_test_products(self, tenant_id: str):
        """Helper to add test products to the real database using new pricing_options model."""
        with get_db_session() as db_session:
            # Sports package with CPM pricing
            create_test_product_with_pricing(
                session=db_session,
                tenant_id=tenant_id,
                product_id="test_db_1",
                name="Database Sports Package",
                description="Sports content advertising package",
                pricing_model="CPM",
                rate="4.50",
                is_fixed=True,
                currency="USD",
                min_spend_per_package="500.0",
                formats=[
                    {"agent_url": "https://test.com", "id": "display_300x250"},
                    {"agent_url": "https://test.com", "id": "display_728x90"},
                ],
                targeting_template={},
                delivery_type="non_guaranteed",
                countries=["US", "CA"],
            )

            # Automotive package with CPM pricing
            create_test_product_with_pricing(
                session=db_session,
                tenant_id=tenant_id,
                product_id="test_db_2",
                name="Database Automotive Package",
                description="Automotive content advertising package",
                pricing_model="CPM",
                rate="5.25",
                is_fixed=True,
                currency="USD",
                min_spend_per_package="750.0",
                formats=[
                    {"agent_url": "https://test.com", "id": "display_300x250"},
                    {"agent_url": "https://test.com", "id": "video_pre_roll"},
                ],
                targeting_template={},
                delivery_type="non_guaranteed",
                countries=["US"],
            )

            db_session.commit()
