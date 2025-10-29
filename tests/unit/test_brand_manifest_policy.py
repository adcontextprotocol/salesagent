"""Tests for brand manifest policy enforcement in get_products."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp.exceptions import ToolError

from src.core.tools.products import _get_products_impl


def mock_apply_testing_hooks(response_data, *args, **kwargs):
    """Mock apply_testing_hooks that just passes through the data."""
    return response_data


def make_async_provider_mock(provider):
    """Create an async function that returns the mock provider."""

    async def mock_get_provider(*args, **kwargs):
        return provider

    return mock_get_provider


class TestBrandManifestPolicy:
    """Test brand manifest policy enforcement across different policy modes."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock FastMCP context."""
        context = MagicMock()
        context.headers = {}
        return context

    @pytest.fixture
    def mock_tenant_require_brand(self):
        """Mock tenant with require_brand policy (strictest)."""
        return {
            "tenant_id": "test_tenant",
            "brand_manifest_policy": "require_brand",
            "advertising_policy": {"enabled": False},
        }

    @pytest.fixture
    def mock_tenant_require_auth(self):
        """Mock tenant with require_auth policy (middle)."""
        return {
            "tenant_id": "test_tenant",
            "brand_manifest_policy": "require_auth",
            "advertising_policy": {"enabled": False},
        }

    @pytest.fixture
    def mock_tenant_public(self):
        """Mock tenant with public policy (most permissive)."""
        return {
            "tenant_id": "test_tenant",
            "brand_manifest_policy": "public",
            "advertising_policy": {"enabled": False},
        }

    @pytest.fixture
    def mock_product_catalog_provider(self):
        """Mock product catalog provider."""
        provider = AsyncMock()
        provider.get_products = AsyncMock(return_value=[])
        return provider

    @pytest.mark.asyncio
    async def test_require_brand_policy_rejects_unauthenticated(self, mock_context, mock_tenant_require_brand):
        """Test that require_brand policy rejects unauthenticated requests."""
        request = MagicMock()
        request.brief = "Test brief"
        request.brand_manifest = None
        request.filters = None
        request.min_exposures = None  # Important: prevent MagicMock from creating this

        with patch(
            "src.core.tools.products.get_principal_from_context",
            return_value=(None, mock_tenant_require_brand),
        ):
            with pytest.raises(ToolError) as exc_info:
                await _get_products_impl(request, mock_context)

            assert "Authentication required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_require_brand_policy_rejects_no_brand_manifest(
        self, mock_context, mock_tenant_require_brand, mock_product_catalog_provider
    ):
        """Test that require_brand policy rejects requests without brand_manifest."""
        request = MagicMock()
        request.brief = "Test brief"
        request.brand_manifest = None
        request.filters = None
        request.min_exposures = None  # Important: prevent MagicMock from creating this

        with patch(
            "src.core.tools.products.get_principal_from_context",
            return_value=("principal_123", mock_tenant_require_brand),
        ):
            with patch("src.core.tools.products.get_principal_object", return_value=None):
                with pytest.raises(ToolError) as exc_info:
                    await _get_products_impl(request, mock_context)

                assert "brand_manifest required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_require_auth_policy_rejects_unauthenticated(self, mock_context, mock_tenant_require_auth):
        """Test that require_auth policy rejects unauthenticated requests."""
        request = MagicMock()
        request.brief = "Test brief"
        request.brand_manifest = None
        request.filters = None
        request.min_exposures = None  # Important: prevent MagicMock from creating this

        with patch(
            "src.core.tools.products.get_principal_from_context",
            return_value=(None, mock_tenant_require_auth),
        ):
            with pytest.raises(ToolError) as exc_info:
                await _get_products_impl(request, mock_context)

            assert "Authentication required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_require_auth_policy_allows_authenticated_no_brand_manifest(
        self, mock_context, mock_tenant_require_auth, mock_product_catalog_provider
    ):
        """Test that require_auth policy allows authenticated requests without brand_manifest."""
        from src.core.schemas import Product

        mock_products = [
            Product(
                product_id="prod_1",
                name="Test Product",
                description="Test",
                formats=["display_300x250"],
                delivery_type="guaranteed",
                pricing_options=[],
                property_tags=["all_inventory"],
            )
        ]

        request = MagicMock()
        request.brief = "Test brief"
        request.brand_manifest = None
        request.filters = None
        request.min_exposures = None  # Important: prevent MagicMock from creating this

        with (
            patch(
                "src.core.tools.products.get_principal_from_context",
                return_value=("principal_123", mock_tenant_require_auth),
            ),
            patch("src.core.tools.products.get_principal_object", return_value=None),
            patch("src.core.tools.products.set_current_tenant"),
            patch(
                "src.core.tools.products.get_product_catalog_provider",
                side_effect=make_async_provider_mock(mock_product_catalog_provider),
            ),
            patch("src.core.tools.products.apply_testing_hooks", side_effect=mock_apply_testing_hooks),
        ):
            mock_product_catalog_provider.get_products.return_value = mock_products
            response = await _get_products_impl(request, mock_context)

            # Should succeed with products (no brand manifest required)
            assert len(response.products) == 1

    @pytest.mark.asyncio
    async def test_public_policy_allows_unauthenticated(
        self, mock_context, mock_tenant_public, mock_product_catalog_provider
    ):
        """Test that public policy allows unauthenticated requests."""
        from src.core.schemas import Product

        mock_products = [
            Product(
                product_id="prod_1",
                name="Test Product",
                description="Test",
                formats=["display_300x250"],
                delivery_type="guaranteed",
                pricing_options=[],
                property_tags=["all_inventory"],
            )
        ]

        request = MagicMock()
        request.brief = "Test brief"
        request.brand_manifest = None
        request.filters = None
        request.min_exposures = None  # Important: prevent MagicMock from creating this

        with (
            patch(
                "src.core.tools.products.get_principal_from_context",
                return_value=(None, mock_tenant_public),
            ),
            patch("src.core.tools.products.get_principal_object", return_value=None),
            patch(
                "src.core.tools.products.get_product_catalog_provider",
                return_value=mock_product_catalog_provider,
            ),
            patch("src.core.tools.products.apply_testing_hooks", side_effect=mock_apply_testing_hooks),
        ):
            mock_product_catalog_provider.get_products.return_value = mock_products
            response = await _get_products_impl(request, mock_context)

            # Should succeed with products (public policy)
            assert len(response.products) == 1
            # Pricing should be hidden for unauthenticated user
            assert response.products[0].pricing_options == []

    @pytest.mark.asyncio
    async def test_public_policy_hides_pricing_even_for_authenticated(
        self, mock_context, mock_tenant_public, mock_product_catalog_provider
    ):
        """Test that public policy hides pricing even for authenticated users."""
        from src.core.schemas import PricingOption, Product

        mock_products = [
            Product(
                product_id="prod_1",
                name="Test Product",
                description="Test",
                formats=["display_300x250"],
                delivery_type="guaranteed",
                pricing_options=[
                    PricingOption(
                        pricing_option_id="cpm_usd_fixed",
                        pricing_model="cpm",
                        rate=5.0,
                        currency="USD",
                        is_fixed=True,
                    )
                ],
                property_tags=["all_inventory"],
            )
        ]

        request = MagicMock()
        request.brief = "Test brief"
        request.brand_manifest = {"name": "Test Brand"}
        request.filters = None
        request.min_exposures = None  # Important: prevent MagicMock from creating this

        with (
            patch(
                "src.core.tools.products.get_principal_from_context",
                return_value=("principal_123", mock_tenant_public),
            ),
            patch("src.core.tools.products.get_principal_object", return_value=None),
            patch("src.core.tools.products.set_current_tenant"),
            patch(
                "src.core.tools.products.get_product_catalog_provider",
                side_effect=make_async_provider_mock(mock_product_catalog_provider),
            ),
            patch("src.core.tools.products.apply_testing_hooks", side_effect=mock_apply_testing_hooks),
        ):
            mock_product_catalog_provider.get_products.return_value = mock_products
            response = await _get_products_impl(request, mock_context)

            # Should succeed with products
            assert len(response.products) == 1
            # Pricing should be hidden even for authenticated user (public policy)
            assert response.products[0].pricing_options == []

    @pytest.mark.asyncio
    async def test_require_auth_policy_shows_pricing_for_authenticated(
        self, mock_context, mock_tenant_require_auth, mock_product_catalog_provider
    ):
        """Test that require_auth policy shows pricing for authenticated users."""
        from src.core.schemas import PricingOption, Product

        mock_products = [
            Product(
                product_id="prod_1",
                name="Test Product",
                description="Test",
                formats=["display_300x250"],
                delivery_type="guaranteed",
                pricing_options=[
                    PricingOption(
                        pricing_option_id="cpm_usd_fixed",
                        pricing_model="cpm",
                        rate=5.0,
                        currency="USD",
                        is_fixed=True,
                    )
                ],
                property_tags=["all_inventory"],
            )
        ]

        request = MagicMock()
        request.brief = "Test brief"
        request.brand_manifest = None
        request.filters = None
        request.min_exposures = None  # Important: prevent MagicMock from creating this

        with (
            patch(
                "src.core.tools.products.get_principal_from_context",
                return_value=("principal_123", mock_tenant_require_auth),
            ),
            patch("src.core.tools.products.get_principal_object", return_value=None),
            patch("src.core.tools.products.set_current_tenant"),
            patch(
                "src.core.tools.products.get_product_catalog_provider",
                return_value=mock_product_catalog_provider,
            ),
            patch("src.core.tools.products.apply_testing_hooks", side_effect=mock_apply_testing_hooks),
        ):
            mock_product_catalog_provider.get_products.return_value = mock_products
            response = await _get_products_impl(request, mock_context)

            # Should succeed with products
            assert len(response.products) == 1
            # Pricing should be shown for authenticated user
            assert len(response.products[0].pricing_options) == 1
            assert response.products[0].pricing_options[0].rate == 5.0

    @pytest.mark.asyncio
    async def test_require_brand_policy_shows_pricing_with_brand_manifest(
        self, mock_context, mock_tenant_require_brand, mock_product_catalog_provider
    ):
        """Test that require_brand policy shows pricing when both auth and brand_manifest provided."""
        from src.core.schemas import PricingOption, Product

        mock_products = [
            Product(
                product_id="prod_1",
                name="Test Product",
                description="Test",
                formats=["display_300x250"],
                delivery_type="guaranteed",
                pricing_options=[
                    PricingOption(
                        pricing_option_id="cpm_usd_fixed",
                        pricing_model="cpm",
                        rate=5.0,
                        currency="USD",
                        is_fixed=True,
                    )
                ],
                property_tags=["all_inventory"],
            )
        ]

        request = MagicMock()
        request.brief = "Test brief"
        request.brand_manifest = {"name": "Test Brand"}
        request.filters = None
        request.min_exposures = None  # Important: prevent MagicMock from creating this

        with (
            patch(
                "src.core.tools.products.get_principal_from_context",
                return_value=("principal_123", mock_tenant_require_brand),
            ),
            patch("src.core.tools.products.get_principal_object", return_value=None),
            patch("src.core.tools.products.set_current_tenant"),
            patch(
                "src.core.tools.products.get_product_catalog_provider",
                side_effect=make_async_provider_mock(mock_product_catalog_provider),
            ),
            patch("src.core.tools.products.apply_testing_hooks", side_effect=mock_apply_testing_hooks),
        ):
            mock_product_catalog_provider.get_products.return_value = mock_products
            response = await _get_products_impl(request, mock_context)

            # Should succeed with products
            assert len(response.products) == 1
            # Pricing should be shown (auth + brand manifest provided)
            assert len(response.products[0].pricing_options) == 1
            assert response.products[0].pricing_options[0].rate == 5.0
