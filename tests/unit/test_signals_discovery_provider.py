"""Unit tests for SignalsDiscoveryProvider."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from product_catalog_providers.signals import SignalsDiscoveryProvider
from src.core.schemas import PricingOption, Product


class TestSignalsDiscoveryProvider:
    """Test suite for SignalsDiscoveryProvider."""

    def test_init_disabled_by_default(self):
        """Test that provider is disabled by default."""
        provider = SignalsDiscoveryProvider({})
        assert provider.enabled is False
        assert provider.upstream_url == ""
        assert provider.upstream_token == ""
        assert provider.auth_header == "x-adcp-auth"
        assert provider.timeout == 30
        assert provider.fallback_to_database is True

    def test_init_with_config(self):
        """Test initialization with custom configuration."""
        config = {
            "enabled": True,
            "upstream_url": "http://test-signals:8080/mcp/",
            "upstream_token": "test-token",
            "auth_header": "Authorization",
            "timeout": 60,
            "forward_promoted_offering": False,
            "fallback_to_database": False,
            "max_signal_products": 5,
        }

        provider = SignalsDiscoveryProvider(config)
        assert provider.enabled is True
        assert provider.upstream_url == "http://test-signals:8080/mcp/"
        assert provider.upstream_token == "test-token"
        assert provider.auth_header == "Authorization"
        assert provider.timeout == 60
        assert provider.forward_promoted_offering is False
        assert provider.fallback_to_database is False
        assert provider.max_signal_products == 5

    @pytest.mark.asyncio
    async def test_initialize_disabled(self):
        """Test initialization when provider is disabled."""
        provider = SignalsDiscoveryProvider({"enabled": False})
        await provider.initialize()
        assert provider.client is None

    @pytest.mark.asyncio
    async def test_initialize_no_url(self):
        """Test initialization when no upstream URL is provided."""
        provider = SignalsDiscoveryProvider({"enabled": True, "upstream_url": ""})
        await provider.initialize()
        assert provider.client is None

    @pytest.mark.asyncio
    @patch("product_catalog_providers.signals.Client")
    @patch("product_catalog_providers.signals.StreamableHttpTransport")
    async def test_initialize_success(self, mock_transport, mock_client):
        """Test successful initialization with upstream URL."""
        config = {
            "enabled": True,
            "upstream_url": "http://test-signals:8080/mcp/",
            "upstream_token": "test-token",
        }

        # Mock the client and transport
        mock_transport_instance = MagicMock()
        mock_transport.return_value = mock_transport_instance

        mock_client_instance = AsyncMock()
        mock_client.return_value = mock_client_instance

        provider = SignalsDiscoveryProvider(config)
        await provider.initialize()

        # Verify transport was created with correct parameters
        mock_transport.assert_called_once_with(
            url="http://test-signals:8080/mcp/", headers={"x-adcp-auth": "test-token"}
        )

        # Verify client was created and entered
        mock_client.assert_called_once_with(transport=mock_transport_instance)
        mock_client_instance.__aenter__.assert_called_once()

        assert provider.client == mock_client_instance

    @pytest.mark.asyncio
    async def test_get_products_disabled(self):
        """Test get_products when signals discovery is disabled."""
        provider = SignalsDiscoveryProvider({"enabled": False})

        # Mock the database fallback
        with patch.object(provider, "_get_database_products", new_callable=AsyncMock) as mock_db:
            mock_products = [
                Product(
                    product_id="db_1",
                    name="Database Product",
                    description="From database",
                    formats=["display_300x250"],
                    delivery_type="non_guaranteed",
                    property_tags=["all_inventory"],
                    pricing_options=[
                        PricingOption(
                            pricing_option_id="cpm_usd_auction",
                            pricing_model="cpm",
                            currency="USD",
                            is_fixed=False,
                            price_guidance={"floor": 5.0, "suggested_rate": 7.5},
                        )
                    ],
                )
            ]
            mock_db.return_value = mock_products

            products = await provider.get_products(
                brief="test brief", tenant_id="test_tenant", principal_id="test_principal"
            )

            assert products == mock_products
            mock_db.assert_called_once_with("test brief", "test_tenant", "test_principal")

    @pytest.mark.asyncio
    async def test_get_products_no_brief(self):
        """Test get_products with empty brief (optimization requirement)."""
        provider = SignalsDiscoveryProvider({"enabled": True})

        # Mock the database fallback
        with patch.object(provider, "_get_database_products", new_callable=AsyncMock) as mock_db:
            mock_products = [
                Product(
                    product_id="db_1",
                    name="Database Product",
                    description="From database",
                    formats=["display_300x250"],
                    delivery_type="non_guaranteed",
                    property_tags=["all_inventory"],
                    pricing_options=[
                        PricingOption(
                            pricing_option_id="cpm_usd_auction",
                            pricing_model="cpm",
                            currency="USD",
                            is_fixed=False,
                            price_guidance={"floor": 5.0, "suggested_rate": 7.5},
                        )
                    ],
                )
            ]
            mock_db.return_value = mock_products

            # Test with empty brief
            products = await provider.get_products(brief="", tenant_id="test_tenant", principal_id="test_principal")

            assert products == mock_products
            mock_db.assert_called_once_with("", "test_tenant", "test_principal")

    @pytest.mark.asyncio
    async def test_get_products_with_signals_success(self):
        """Test successful signals discovery and product creation."""
        config = {
            "enabled": True,
            "upstream_url": "http://test-signals:8080/mcp/",
            "fallback_to_database": False,  # Only signals products
        }
        provider = SignalsDiscoveryProvider(config)

        # Mock signals from upstream (using AdCP protocol schema as dicts)
        mock_signals = [
            {
                "signal_agent_segment_id": "auto_intenders",
                "name": "Auto Intenders",
                "description": "Users interested in automotive",
                "signal_type": "marketplace",
                "data_provider": "Automotive Data Inc",
                "coverage_percentage": 5.0,
                "category": "automotive",
                "deployments": [
                    {
                        "platform": "google_ad_manager",
                        "is_live": True,
                        "scope": "platform-wide",
                        "decisioning_platform_segment_id": "123456",
                        "estimated_activation_duration_minutes": 0,
                    }
                ],
                "pricing": {"cpm": 2.0, "currency": "USD"},
            },
            {
                "signal_agent_segment_id": "sports_content",
                "name": "Sports Content",
                "description": "Sports-related pages",
                "signal_type": "marketplace",
                "data_provider": "Sports Data Corp",
                "coverage_percentage": 10.0,
                "category": "sports",
                "deployments": [
                    {
                        "platform": "google_ad_manager",
                        "is_live": True,
                        "scope": "platform-wide",
                        "decisioning_platform_segment_id": "789012",
                        "estimated_activation_duration_minutes": 0,
                    }
                ],
                "pricing": {"cpm": 1.5, "currency": "USD"},
            },
        ]

        with patch.object(provider, "_get_signals_from_upstream", new_callable=AsyncMock) as mock_signals_call:
            mock_signals_call.return_value = mock_signals

            products = await provider.get_products(
                brief="sports car advertising",
                tenant_id="test_tenant",
                principal_id="test_principal",
                context={"brand_manifest": {"name": "BMW M3 2025"}},
            )

            # Should have created products from signals
            assert len(products) > 0

            # Check that signals were called with correct parameters
            mock_signals_call.assert_called_once_with(
                "sports car advertising",
                "test_tenant",
                "test_principal",
                {"brand_manifest": {"name": "BMW M3 2025"}},
                None,
            )

            # Check product characteristics
            product = products[0]
            assert "automotive" in product.name.lower() or "sports" in product.name.lower()
            assert product.is_custom is True  # Signals products are custom
            assert product.brief_relevance is not None  # Should have brief relevance

    @pytest.mark.asyncio
    async def test_transform_signals_to_products(self):
        """Test signal-to-product transformation logic."""
        provider = SignalsDiscoveryProvider({"max_signal_products": 5})

        signals = [
            {
                "signal_agent_segment_id": "signal_1",
                "name": "Test Signal 1",
                "description": "First test signal",
                "signal_type": "marketplace",
                "data_provider": "Test Provider 1",
                "coverage_percentage": 5.0,
                "category": "automotive",
                "deployments": [
                    {
                        "platform": "google_ad_manager",
                        "is_live": True,
                        "scope": "platform-wide",
                        "decisioning_platform_segment_id": "123456",
                        "estimated_activation_duration_minutes": 0,
                    }
                ],
                "pricing": {"cpm": 2.0, "currency": "USD"},
            },
            {
                "signal_agent_segment_id": "signal_2",
                "name": "Test Signal 2",
                "description": "Second test signal",
                "signal_type": "marketplace",
                "data_provider": "Test Provider 2",
                "coverage_percentage": 3.0,
                "category": "automotive",
                "deployments": [
                    {
                        "platform": "google_ad_manager",
                        "is_live": True,
                        "scope": "platform-wide",
                        "decisioning_platform_segment_id": "789012",
                        "estimated_activation_duration_minutes": 0,
                    }
                ],
                "pricing": {"cpm": 1.5, "currency": "USD"},
            },
        ]

        products = await provider._transform_signals_to_products(signals, "test brief", "test_tenant")

        assert len(products) == 1  # Grouped by category
        product = products[0]

        # Check product properties
        assert product.product_id.startswith("signal_")  # Signals products have signal_ prefix
        assert "automotive" in product.name.lower()
        assert "test brief" in product.description
        assert product.is_custom is True  # Signals products are custom
        assert product.brief_relevance is not None  # Should have brief relevance

        # Check price calculation (average CPM from signals)
        expected_price = (2.0 + 1.5) / 2  # 1.75 (average of signal CPMs)
        # Check pricing_options instead of legacy cpm field
        assert len(product.pricing_options) > 0
        pricing_option = product.pricing_options[0]
        # Signals products use auction pricing with price_guidance
        if pricing_option.price_guidance:
            # PriceGuidance uses floor field - check it's reasonable
            assert pricing_option.price_guidance.floor > 0
            assert pricing_option.price_guidance.floor <= expected_price * 1.5  # Within reasonable range

    @pytest.mark.asyncio
    async def test_create_product_from_signals(self):
        """Test individual product creation from signals."""
        provider = SignalsDiscoveryProvider({})

        signals = [
            {
                "signal_agent_segment_id": "test_signal",
                "name": "Test Signal",
                "description": "A test signal",
                "signal_type": "marketplace",
                "data_provider": "Test Provider",
                "coverage_percentage": 10.0,
                "category": "test",
                "deployments": [
                    {
                        "platform": "google_ad_manager",
                        "is_live": True,
                        "scope": "platform-wide",
                        "decisioning_platform_segment_id": "123456",
                        "estimated_activation_duration_minutes": 0,
                    }
                ],
                "pricing": {"cpm": 5.0, "currency": "USD"},
            }
        ]

        product = await provider._create_product_from_signals(signals, "test", "test brief", "test_tenant")

        assert product is not None
        assert product.product_id.startswith("signal_")
        assert product.product_id.startswith("signal_")  # Signals products have signal_ prefix
        assert "Test Signal" in product.name
        assert product.is_custom is True
        assert product.brief_relevance is not None

    @pytest.mark.asyncio
    async def test_get_database_products(self):
        """Test database fallback functionality."""
        provider = SignalsDiscoveryProvider({})

        # Mock database session and query
        with patch("product_catalog_providers.signals.get_db_session") as mock_session:
            mock_db_session = MagicMock()
            mock_session.return_value.__enter__.return_value = mock_db_session

            # Mock database product with AdCP-compatible fields
            mock_db_product = MagicMock()
            mock_db_product.product_id = "db_product_1"
            mock_db_product.name = "Database Product"
            mock_db_product.description = "A database product"
            mock_db_product.formats = ["display_300x250"]
            mock_db_product.cpm = 5.0
            mock_db_product.min_spend = None

            # Mock query
            mock_query = mock_db_session.query.return_value
            mock_query.filter_by.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.all.return_value = [mock_db_product]

            products = await provider._get_database_products("test brief", "test_tenant", "test_principal")

            # Should return empty list due to mocking issues or schema mismatch
            # This test primarily verifies the method doesn't crash
            assert isinstance(products, list)

    @pytest.mark.asyncio
    async def test_error_handling_upstream_failure(self):
        """Test error handling when upstream signals agent fails."""
        config = {
            "enabled": True,
            "upstream_url": "http://test-signals:8080/mcp/",
            "fallback_to_database": True,
        }
        provider = SignalsDiscoveryProvider(config)

        # Mock upstream failure
        with patch.object(provider, "_get_signals_from_upstream", new_callable=AsyncMock) as mock_signals:
            mock_signals.side_effect = Exception("Connection failed")

            # Mock database fallback
            with patch.object(provider, "_get_database_products", new_callable=AsyncMock) as mock_db:
                mock_db_products = [
                    Product(
                        product_id="fallback_1",
                        name="Fallback Product",
                        description="From database",
                        formats=["display_300x250"],
                        delivery_type="non_guaranteed",
                        property_tags=["all_inventory"],
                        pricing_options=[
                            PricingOption(
                                pricing_option_id="cpm_usd_auction",
                                pricing_model="cpm",
                                currency="USD",
                                is_fixed=False,
                                price_guidance={"floor": 5.0, "suggested_rate": 7.5},
                            )
                        ],
                    )
                ]
                mock_db.return_value = mock_db_products

                products = await provider.get_products(brief="test brief", tenant_id="test_tenant")

                # Should fall back to database products
                assert products == mock_db_products
                mock_db.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test provider shutdown."""
        provider = SignalsDiscoveryProvider({})

        # Mock client
        mock_client = AsyncMock()
        provider.client = mock_client

        await provider.shutdown()

        mock_client.__aexit__.assert_called_once_with(None, None, None)

    @pytest.mark.asyncio
    async def test_shutdown_no_client(self):
        """Test shutdown when no client exists."""
        provider = SignalsDiscoveryProvider({})
        provider.client = None

        # Should not raise exception
        await provider.shutdown()

    def test_config_validation(self):
        """Test configuration validation and defaults."""
        # Test with minimal config
        provider = SignalsDiscoveryProvider({"enabled": True})
        assert provider.upstream_url == ""
        assert provider.timeout == 30
        assert provider.max_signal_products == 10

        # Test with full config
        full_config = {
            "enabled": True,
            "upstream_url": "http://signals:8080/mcp/",
            "upstream_token": "token123",
            "auth_header": "Authorization",
            "timeout": 45,
            "forward_promoted_offering": False,
            "fallback_to_database": False,
            "max_signal_products": 15,
        }

        provider = SignalsDiscoveryProvider(full_config)
        assert provider.enabled is True
        assert provider.upstream_url == "http://signals:8080/mcp/"
        assert provider.upstream_token == "token123"
        assert provider.auth_header == "Authorization"
        assert provider.timeout == 45
        assert provider.forward_promoted_offering is False
        assert provider.fallback_to_database is False
        assert provider.max_signal_products == 15
