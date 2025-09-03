"""Integration tests for signals agent workflow."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp.server.context import Context

from src.core.database.database_session import get_db_session
from src.core.database.models import Product as ModelProduct
from src.core.database.models import Tenant
from src.core.main import get_products
from src.core.schemas import GetProductsRequest, Signal
from tests.fixtures.builders import create_test_tenant_with_principal


@pytest.mark.asyncio
class TestSignalsAgentWorkflow:
    """Integration tests for signals agent workflow."""

    @pytest.fixture
    async def tenant_with_signals_config(self):
        """Create a test tenant with signals discovery configured."""
        tenant_data = await create_test_tenant_with_principal()
        tenant_id = tenant_data["tenant"]["tenant_id"]

        # Add signals configuration
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
            tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            tenant.signals_agent_config = signals_config
            db_session.commit()

        return tenant_data

    @pytest.fixture
    async def tenant_without_signals_config(self):
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
            Signal(
                signal_id="premium_content",
                name="Premium Content",
                description="High-quality editorial content",
                type="contextual",
                category="content",
                reach=12.0,
                cpm_uplift=1.8,
            ),
        ]

    @pytest.fixture
    def mock_context(self):
        """Create a mock FastMCP context."""
        context = MagicMock(spec=Context)
        context.meta = {"headers": {"x-adcp-auth": "test-token-123", "x-context-id": "test-context-123"}}
        return context

    async def test_get_products_without_signals_config(self, tenant_without_signals_config, mock_context):
        """Test get_products with tenant that has no signals configuration."""
        tenant_data = tenant_without_signals_config
        tenant_id = tenant_data["tenant"]["tenant_id"]
        principal_id = tenant_data["principal"]["principal_id"]

        # Add some database products
        await self._add_test_products(tenant_id)

        request = GetProductsRequest(
            brief="sports car advertising campaign", promoted_offering="BMW M3 2025 sports sedan"
        )

        # Mock context extraction
        with patch("src.core.main._get_principal_id_from_context", return_value=principal_id):
            with patch("src.core.main.get_current_tenant", return_value={"tenant_id": tenant_id}):
                with patch("src.core.main.get_principal_object", return_value=tenant_data["principal"]):
                    with patch("src.core.main.PolicyCheckService") as mock_policy:
                        # Mock policy service
                        mock_policy_instance = mock_policy.return_value
                        mock_policy_instance.check_brief_compliance = AsyncMock(
                            return_value=MagicMock(status="APPROVED", reason="", restrictions=[])
                        )
                        mock_policy_instance.check_product_eligibility = MagicMock(return_value=(True, ""))

                        response = await get_products(request, mock_context)

                        # Should return database products only
                        assert len(response.products) > 0

                        # Verify no signals products (check metadata)
                        for product in response.products:
                            assert product.metadata.get("created_by") != "signals_discovery"

    async def test_get_products_with_signals_config_brief_provided(
        self, tenant_with_signals_config, mock_context, mock_signals_response
    ):
        """Test get_products with signals configuration and brief provided."""
        tenant_data = tenant_with_signals_config
        tenant_id = tenant_data["tenant"]["tenant_id"]
        principal_id = tenant_data["principal"]["principal_id"]

        # Add some database products
        await self._add_test_products(tenant_id)

        request = GetProductsRequest(
            brief="luxury sports car advertising for wealthy professionals",
            promoted_offering="Porsche 911 Turbo S 2025",
        )

        # Mock the upstream signals call
        with patch("product_catalog_providers.signals.Client") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.__aenter__.return_value = mock_client

            # Mock the get_signals tool call
            mock_client.call_tool = AsyncMock(
                return_value={"signals": [signal.model_dump() for signal in mock_signals_response]}
            )

            # Mock context extraction
            with patch("src.core.main._get_principal_id_from_context", return_value=principal_id):
                with patch(
                    "src.core.main.get_current_tenant",
                    return_value={
                        "tenant_id": tenant_id,
                        "signals_agent_config": {
                            "enabled": True,
                            "upstream_url": "http://test-signals:8080/mcp/",
                            "upstream_token": "test-token",
                            "auth_header": "x-adcp-auth",
                            "timeout": 30,
                            "forward_promoted_offering": True,
                            "fallback_to_database": True,
                        },
                    },
                ):
                    with patch("src.core.main.get_principal_object", return_value=tenant_data["principal"]):
                        with patch("src.core.main.PolicyCheckService") as mock_policy:
                            # Mock policy service
                            mock_policy_instance = mock_policy.return_value
                            mock_policy_instance.check_brief_compliance = AsyncMock(
                                return_value=MagicMock(status="APPROVED", reason="", restrictions=[])
                            )
                            mock_policy_instance.check_product_eligibility = MagicMock(return_value=(True, ""))

                            response = await get_products(request, mock_context)

                            # Should return both signals and database products
                            assert len(response.products) > 0

                            # Verify signals products are included
                            signals_products = [
                                p for p in response.products if p.metadata.get("created_by") == "signals_discovery"
                            ]
                            assert len(signals_products) > 0

                            # Verify signals product characteristics
                            signals_product = signals_products[0]
                            assert (
                                "sports" in signals_product.name.lower() or "automotive" in signals_product.name.lower()
                            )
                            assert signals_product.targeting_overlay is not None
                            assert "signals" in signals_product.targeting_overlay

                            # Verify upstream was called with correct parameters
                            mock_client.call_tool.assert_called_once_with(
                                "get_signals",
                                {
                                    "brief": "luxury sports car advertising for wealthy professionals",
                                    "tenant_id": tenant_id,
                                    "principal_id": principal_id,
                                    "principal_data": tenant_data["principal"].model_dump(),
                                    "context": {
                                        "promoted_offering": "Porsche 911 Turbo S 2025",
                                        "tenant_id": tenant_id,
                                        "principal_id": principal_id,
                                    },
                                    "promoted_offering": "Porsche 911 Turbo S 2025",
                                },
                            )

    async def test_get_products_with_signals_config_no_brief(self, tenant_with_signals_config, mock_context):
        """Test that no signals call is made when brief is empty (optimization requirement)."""
        tenant_data = tenant_with_signals_config
        tenant_id = tenant_data["tenant"]["tenant_id"]
        principal_id = tenant_data["principal"]["principal_id"]

        # Add some database products
        await self._add_test_products(tenant_id)

        request = GetProductsRequest(brief="", promoted_offering="Generic Product 2025")  # Empty brief

        # Mock the upstream signals call to ensure it's NOT called
        with patch("product_catalog_providers.signals.Client") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.__aenter__.return_value = mock_client
            mock_client.call_tool = AsyncMock()

            # Mock context extraction
            with patch("src.core.main._get_principal_id_from_context", return_value=principal_id):
                with patch(
                    "src.core.main.get_current_tenant",
                    return_value={
                        "tenant_id": tenant_id,
                        "signals_agent_config": {
                            "enabled": True,
                            "upstream_url": "http://test-signals:8080/mcp/",
                            "upstream_token": "test-token",
                        },
                    },
                ):
                    with patch("src.core.main.get_principal_object", return_value=tenant_data["principal"]):
                        with patch("src.core.main.PolicyCheckService") as mock_policy:
                            # Mock policy service
                            mock_policy_instance = mock_policy.return_value
                            mock_policy_instance.check_brief_compliance = AsyncMock(
                                return_value=MagicMock(status="APPROVED", reason="", restrictions=[])
                            )
                            mock_policy_instance.check_product_eligibility = MagicMock(return_value=(True, ""))

                            response = await get_products(request, mock_context)

                            # Should return database products only
                            assert len(response.products) > 0

                            # Verify no signals products
                            signals_products = [
                                p for p in response.products if p.metadata.get("created_by") == "signals_discovery"
                            ]
                            assert len(signals_products) == 0

                            # Verify upstream was NOT called (optimization)
                            mock_client.call_tool.assert_not_called()

    async def test_get_products_signals_upstream_failure_with_fallback(self, tenant_with_signals_config, mock_context):
        """Test fallback behavior when upstream signals agent fails."""
        tenant_data = tenant_with_signals_config
        tenant_id = tenant_data["tenant"]["tenant_id"]
        principal_id = tenant_data["principal"]["principal_id"]

        # Add some database products
        await self._add_test_products(tenant_id)

        request = GetProductsRequest(brief="test brief for failure scenario", promoted_offering="Test Product 2025")

        # Mock upstream failure
        with patch("product_catalog_providers.signals.Client") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.__aenter__.return_value = mock_client

            # Make upstream call fail
            mock_client.call_tool = AsyncMock(side_effect=Exception("Connection timeout"))

            # Mock context extraction
            with patch("src.core.main._get_principal_id_from_context", return_value=principal_id):
                with patch(
                    "src.core.main.get_current_tenant",
                    return_value={
                        "tenant_id": tenant_id,
                        "signals_agent_config": {
                            "enabled": True,
                            "upstream_url": "http://test-signals:8080/mcp/",
                            "upstream_token": "test-token",
                            "fallback_to_database": True,
                        },
                    },
                ):
                    with patch("src.core.main.get_principal_object", return_value=tenant_data["principal"]):
                        with patch("src.core.main.PolicyCheckService") as mock_policy:
                            # Mock policy service
                            mock_policy_instance = mock_policy.return_value
                            mock_policy_instance.check_brief_compliance = AsyncMock(
                                return_value=MagicMock(status="APPROVED", reason="", restrictions=[])
                            )
                            mock_policy_instance.check_product_eligibility = MagicMock(return_value=(True, ""))

                            response = await get_products(request, mock_context)

                            # Should still return database products due to fallback
                            assert len(response.products) > 0

                            # All products should be from database (no signals products)
                            signals_products = [
                                p for p in response.products if p.metadata.get("created_by") == "signals_discovery"
                            ]
                            assert len(signals_products) == 0

    async def test_hybrid_product_ranking(self, tenant_with_signals_config, mock_context, mock_signals_response):
        """Test that signals products are ranked first in hybrid provider."""
        tenant_data = tenant_with_signals_config
        tenant_id = tenant_data["tenant"]["tenant_id"]
        principal_id = tenant_data["principal"]["principal_id"]

        # Add some database products
        await self._add_test_products(tenant_id)

        request = GetProductsRequest(
            brief="comprehensive test for product ranking", promoted_offering="Test Product 2025"
        )

        # Mock the upstream signals call
        with patch("product_catalog_providers.signals.Client") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.__aenter__.return_value = mock_client

            mock_client.call_tool = AsyncMock(
                return_value={"signals": [signal.model_dump() for signal in mock_signals_response]}
            )

            # Mock context extraction
            with patch("src.core.main._get_principal_id_from_context", return_value=principal_id):
                with patch(
                    "src.core.main.get_current_tenant",
                    return_value={
                        "tenant_id": tenant_id,
                        "signals_agent_config": {
                            "enabled": True,
                            "upstream_url": "http://test-signals:8080/mcp/",
                            "upstream_token": "test-token",
                            "fallback_to_database": True,
                        },
                    },
                ):
                    with patch("src.core.main.get_principal_object", return_value=tenant_data["principal"]):
                        with patch("src.core.main.PolicyCheckService") as mock_policy:
                            # Mock policy service
                            mock_policy_instance = mock_policy.return_value
                            mock_policy_instance.check_brief_compliance = AsyncMock(
                                return_value=MagicMock(status="APPROVED", reason="", restrictions=[])
                            )
                            mock_policy_instance.check_product_eligibility = MagicMock(return_value=(True, ""))

                            response = await get_products(request, mock_context)

                            assert len(response.products) > 0

                            # Find signals and database products
                            signals_products = []
                            database_products = []

                            for product in response.products:
                                if product.metadata.get("created_by") == "signals_discovery":
                                    signals_products.append(product)
                                else:
                                    database_products.append(product)

                            # Should have both types
                            assert len(signals_products) > 0
                            assert len(database_products) > 0

                            # Signals products should come first (signals_first ranking)
                            first_signals_index = next(
                                i
                                for i, p in enumerate(response.products)
                                if p.metadata.get("created_by") == "signals_discovery"
                            )
                            first_database_index = next(
                                i
                                for i, p in enumerate(response.products)
                                if p.metadata.get("created_by") != "signals_discovery"
                            )

                            assert first_signals_index < first_database_index

    async def _add_test_products(self, tenant_id: str):
        """Helper to add test products to the database."""
        with get_db_session() as db_session:
            products = [
                ModelProduct(
                    product_id="test_db_1",
                    tenant_id=tenant_id,
                    name="Database Sports Package",
                    description="Sports content advertising package",
                    product_type="programmatic",
                    formats=["display_300x250", "display_728x90"],
                    price_model="cpm",
                    base_price=4.50,
                    min_spend=500.0,
                    countries=["US", "CA"],
                    targeting_template={},
                    targeting_overlay={},
                    is_active=True,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                ),
                ModelProduct(
                    product_id="test_db_2",
                    tenant_id=tenant_id,
                    name="Database Automotive Package",
                    description="Automotive content advertising package",
                    product_type="programmatic",
                    formats=["display_300x250", "video_pre_roll"],
                    price_model="cpm",
                    base_price=5.25,
                    min_spend=750.0,
                    countries=["US"],
                    targeting_template={},
                    targeting_overlay={},
                    is_active=True,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                ),
            ]

            for product in products:
                db_session.add(product)
            db_session.commit()

    async def test_signals_product_characteristics(
        self, tenant_with_signals_config, mock_context, mock_signals_response
    ):
        """Test that signals products have expected characteristics."""
        tenant_data = tenant_with_signals_config
        tenant_id = tenant_data["tenant"]["tenant_id"]
        principal_id = tenant_data["principal"]["principal_id"]

        request = GetProductsRequest(
            brief="detailed test for signals product features", promoted_offering="Feature Test Product 2025"
        )

        # Mock the upstream signals call
        with patch("product_catalog_providers.signals.Client") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.__aenter__.return_value = mock_client

            mock_client.call_tool = AsyncMock(
                return_value={"signals": [signal.model_dump() for signal in mock_signals_response]}
            )

            # Mock context extraction
            with patch("src.core.main._get_principal_id_from_context", return_value=principal_id):
                with patch(
                    "src.core.main.get_current_tenant",
                    return_value={
                        "tenant_id": tenant_id,
                        "signals_agent_config": {
                            "enabled": True,
                            "upstream_url": "http://test-signals:8080/mcp/",
                            "upstream_token": "test-token",
                            "fallback_to_database": False,  # Only signals products
                        },
                    },
                ):
                    with patch("src.core.main.get_principal_object", return_value=tenant_data["principal"]):
                        with patch("src.core.main.PolicyCheckService") as mock_policy:
                            # Mock policy service
                            mock_policy_instance = mock_policy.return_value
                            mock_policy_instance.check_brief_compliance = AsyncMock(
                                return_value=MagicMock(status="APPROVED", reason="", restrictions=[])
                            )
                            mock_policy_instance.check_product_eligibility = MagicMock(return_value=(True, ""))

                            response = await get_products(request, mock_context)

                            # Should have signals products only
                            signals_products = [
                                p for p in response.products if p.metadata.get("created_by") == "signals_discovery"
                            ]
                            assert len(signals_products) > 0

                            # Test characteristics of first signals product
                            product = signals_products[0]

                            # Basic product fields
                            assert product.tenant_id == tenant_id
                            assert product.product_id.startswith("signal_")
                            assert product.product_type == "programmatic"
                            assert len(product.formats) > 0
                            assert product.price_model == "cpm"
                            assert product.base_price > 0
                            assert len(product.countries) > 0

                            # Signals-specific fields
                            assert product.targeting_overlay is not None
                            assert "signals" in product.targeting_overlay
                            assert len(product.targeting_overlay["signals"]) > 0
                            assert "signal_category" in product.targeting_overlay

                            # Metadata
                            assert product.metadata["created_by"] == "signals_discovery"
                            assert "signal_count" in product.metadata
                            assert "brief_snippet" in product.metadata
                            assert product.metadata["brief_snippet"] == "detailed test for signals product features"
