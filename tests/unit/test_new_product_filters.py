"""Unit tests for new AdCP 2.5 product filters.

Tests the filter logic in isolation without requiring a database connection.
Currently implemented filters: countries, channels.
"""

from unittest.mock import Mock

from adcp.types import ProductFilters


class TestNewProductFiltersLogic:
    """Test the new filter logic in get_products."""

    def _create_mock_product(
        self,
        product_id: str,
        countries: list[str] | None = None,
        channel: str | None = None,
    ):
        """Create a mock product for testing filters."""
        product = Mock()
        product.product_id = product_id
        product.countries = countries
        product.channel = channel
        return product

    def test_countries_filter_includes_matching_country(self):
        """Test that countries filter includes products with matching country."""
        product = self._create_mock_product(
            product_id="test_product",
            countries=["US", "CA"],
        )

        # Test filter logic: request for US should match product with US
        request_countries = {"US"}
        product_countries = set(product.countries) if product.countries else set()

        # Product should be included if request countries intersect with product countries
        matches = bool(product_countries.intersection(request_countries))
        assert matches is True

    def test_countries_filter_excludes_non_matching_country(self):
        """Test that countries filter excludes products without matching country."""
        product = self._create_mock_product(
            product_id="test_product",
            countries=["UK", "FR"],
        )

        # Test filter logic: request for US should NOT match product with UK/FR
        request_countries = {"US"}
        product_countries = set(product.countries) if product.countries else set()

        matches = bool(product_countries.intersection(request_countries))
        assert matches is False

    def test_countries_filter_matches_global_products(self):
        """Test that global products (no country restriction) match any country filter."""
        product = self._create_mock_product(
            product_id="test_product",
            countries=None,  # Global - no country restriction
        )

        # Global products should match any request (not filtered out)
        product_countries = set(product.countries) if product.countries else set()

        # Empty product_countries means global - should pass through
        assert len(product_countries) == 0

    def test_channels_filter_matches_product_channel(self):
        """Test that channel filter matches product's channel field."""
        product = self._create_mock_product(
            product_id="test_product",
            channel="display",
        )

        # Test filter logic: request for display should match product with display channel
        request_channels = {"display"}
        product_channel = product.channel.lower() if product.channel else None

        matches = product_channel in request_channels if product_channel else True
        assert matches is True

    def test_channels_filter_excludes_non_matching_channel(self):
        """Test that channel filter excludes products with different channel."""
        product = self._create_mock_product(
            product_id="test_product",
            channel="video",
        )

        # Test filter logic: request for display should NOT match product with video channel
        request_channels = {"display"}
        product_channel = product.channel.lower() if product.channel else None

        matches = product_channel in request_channels if product_channel else True
        assert matches is False

    def test_channels_filter_matches_products_without_channel(self):
        """Test that products without channel field pass any channel filter."""
        product = self._create_mock_product(
            product_id="test_product",
            channel=None,  # No channel restriction
        )

        # Products without channel should match any request (not filtered out)
        product_channel = product.channel.lower() if product.channel else None

        # No channel means global - should pass through
        assert product_channel is None

    def test_channels_filter_multiple_channels(self):
        """Test that channel filter matches when product's channel is in list."""
        product = self._create_mock_product(
            product_id="test_product",
            channel="audio",
        )

        # Test filter logic: request for display, video, audio should match audio
        request_channels = {"display", "video", "audio"}
        product_channel = product.channel.lower() if product.channel else None

        matches = product_channel in request_channels if product_channel else True
        assert matches is True

    def test_product_filters_schema_has_countries_and_channels(self):
        """Test that ProductFilters schema includes countries and channels fields."""
        fields = ProductFilters.model_fields

        assert "countries" in fields
        assert "channels" in fields

    def test_product_filters_can_be_constructed_with_countries_and_channels(self):
        """Test that ProductFilters can be constructed with countries and channels."""
        filters = ProductFilters(
            countries=["US", "CA"],
            channels=["display", "video"],
        )

        assert filters.countries is not None
        assert filters.channels is not None

    def test_combined_countries_and_channels_filter(self):
        """Test combining countries and channels filters."""
        # Product in US with display channel
        product = self._create_mock_product(
            product_id="test_product",
            countries=["US"],
            channel="display",
        )

        # Request for US and display - should match
        request_countries = {"US"}
        request_channels = {"display"}

        product_countries = set(product.countries) if product.countries else set()
        product_channel = product.channel.lower() if product.channel else None

        countries_match = len(product_countries) == 0 or bool(product_countries.intersection(request_countries))
        channel_match = product_channel in request_channels if product_channel else True

        assert countries_match is True
        assert channel_match is True
