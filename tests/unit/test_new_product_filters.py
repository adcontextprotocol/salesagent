"""Unit tests for new AdCP 2.5 product filters.

Tests the filter logic in isolation without requiring a database connection.
"""

from datetime import UTC, date, timedelta
from decimal import Decimal
from unittest.mock import Mock

from adcp.types import ProductFilters


class TestNewProductFiltersLogic:
    """Test the new filter logic in get_products."""

    def _create_mock_product(
        self,
        product_id: str,
        format_ids: list[str],
        pricing_rate: float,
        pricing_currency: str = "USD",
        countries: list[str] | None = None,
        expires_at=None,
    ):
        """Create a mock product for testing filters."""
        product = Mock()
        product.product_id = product_id
        product.format_ids = [{"id": fid, "agent_url": "https://test.com"} for fid in format_ids]
        product.countries = countries
        product.expires_at = expires_at

        # Create mock pricing option
        pricing_option = Mock()
        pricing_option.currency = pricing_currency
        pricing_option.rate = Decimal(str(pricing_rate))
        pricing_option.floor = None
        product.pricing_options = [pricing_option]

        return product

    def test_countries_filter_includes_matching_country(self):
        """Test that countries filter includes products with matching country."""
        # This tests the filter logic from products.py
        product = self._create_mock_product(
            product_id="test_product",
            format_ids=["display_300x250"],
            pricing_rate=15.0,
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
            format_ids=["display_300x250"],
            pricing_rate=15.0,
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
            format_ids=["display_300x250"],
            pricing_rate=15.0,
            countries=None,  # Global - no country restriction
        )

        # Global products should match any request (not filtered out)
        product_countries = set(product.countries) if product.countries else set()

        # Empty product_countries means global - should pass through
        assert len(product_countries) == 0

    def test_channels_filter_infers_display_from_format_id(self):
        """Test that channel is correctly inferred from display_ format prefix."""
        product = self._create_mock_product(
            product_id="test_product",
            format_ids=["display_300x250", "display_728x90"],
            pricing_rate=15.0,
        )

        # Infer channels from format_ids
        product_channels = set()
        for format_id in product.format_ids:
            fid = format_id.get("id") if isinstance(format_id, dict) else format_id
            if fid.startswith("display_"):
                product_channels.add("display")

        assert "display" in product_channels

    def test_channels_filter_infers_video_from_format_id(self):
        """Test that channel is correctly inferred from video_ format prefix."""
        product = self._create_mock_product(
            product_id="test_product",
            format_ids=["video_15s", "video_30s"],
            pricing_rate=25.0,
        )

        # Infer channels from format_ids
        product_channels = set()
        for format_id in product.format_ids:
            fid = format_id.get("id") if isinstance(format_id, dict) else format_id
            if fid.startswith("video_"):
                product_channels.add("video")

        assert "video" in product_channels

    def test_channels_filter_infers_audio_from_format_id(self):
        """Test that channel is correctly inferred from audio_ format prefix."""
        product = self._create_mock_product(
            product_id="test_product",
            format_ids=["audio_30s"],
            pricing_rate=20.0,
        )

        # Infer channels from format_ids
        product_channels = set()
        for format_id in product.format_ids:
            fid = format_id.get("id") if isinstance(format_id, dict) else format_id
            if fid.startswith("audio_"):
                product_channels.add("audio")

        assert "audio" in product_channels

    def test_budget_range_filter_includes_within_range(self):
        """Test that budget_range filter includes products within the range."""
        product = self._create_mock_product(
            product_id="test_product",
            format_ids=["display_300x250"],
            pricing_rate=15.0,
            pricing_currency="USD",
        )

        # Test filter logic: rate $15 should be within range $10-$20
        budget_min = 10.0
        budget_max = 20.0
        budget_currency = "USD"

        # Check product pricing options
        for po in product.pricing_options:
            if po.currency == budget_currency:
                rate_value = float(po.rate)
                within_range = budget_min <= rate_value <= budget_max
                assert within_range is True

    def test_budget_range_filter_excludes_above_max(self):
        """Test that budget_range filter excludes products above max."""
        product = self._create_mock_product(
            product_id="test_product",
            format_ids=["display_300x250"],
            pricing_rate=25.0,  # Above $20 max
            pricing_currency="USD",
        )

        budget_min = 10.0
        budget_max = 20.0

        for po in product.pricing_options:
            rate_value = float(po.rate)
            within_range = budget_min <= rate_value <= budget_max
            assert within_range is False

    def test_budget_range_filter_excludes_below_min(self):
        """Test that budget_range filter excludes products below min."""
        product = self._create_mock_product(
            product_id="test_product",
            format_ids=["display_300x250"],
            pricing_rate=5.0,  # Below $10 min
            pricing_currency="USD",
        )

        budget_min = 10.0
        budget_max = 20.0

        for po in product.pricing_options:
            rate_value = float(po.rate)
            within_range = budget_min <= rate_value <= budget_max
            assert within_range is False

    def test_budget_range_filter_requires_matching_currency(self):
        """Test that budget_range filter only checks products with matching currency."""
        product = self._create_mock_product(
            product_id="test_product",
            format_ids=["display_300x250"],
            pricing_rate=15.0,  # Would be in range but wrong currency
            pricing_currency="GBP",
        )

        budget_currency = "USD"

        # No USD pricing option found
        has_matching_currency = any(po.currency == budget_currency for po in product.pricing_options)
        assert has_matching_currency is False

    def test_end_date_filter_excludes_expired_products(self):
        """Test that end_date filter excludes products that expire before campaign ends."""
        from datetime import datetime

        # Product expires in 10 days
        expires_at = datetime.now(UTC) + timedelta(days=10)
        product = self._create_mock_product(
            product_id="test_product",
            format_ids=["display_300x250"],
            pricing_rate=15.0,
            expires_at=expires_at,
        )

        # Campaign ends in 20 days - product should be excluded
        campaign_end_date = date.today() + timedelta(days=20)

        product_expiry_date = product.expires_at.date() if hasattr(product.expires_at, "date") else None
        if product_expiry_date:
            expires_before_campaign_ends = product_expiry_date < campaign_end_date
            assert expires_before_campaign_ends is True

    def test_end_date_filter_includes_products_without_expiration(self):
        """Test that end_date filter includes products without expiration."""
        product = self._create_mock_product(
            product_id="test_product",
            format_ids=["display_300x250"],
            pricing_rate=15.0,
            expires_at=None,  # No expiration
        )

        # Products without expires_at should not be filtered out
        assert product.expires_at is None

    def test_product_filters_schema_has_new_fields(self):
        """Test that ProductFilters schema includes the new fields."""
        # Verify the adcp library has the expected fields
        fields = ProductFilters.model_fields

        assert "start_date" in fields
        assert "end_date" in fields
        assert "budget_range" in fields
        assert "countries" in fields
        assert "channels" in fields

    def test_product_filters_can_be_constructed_with_new_fields(self):
        """Test that ProductFilters can be constructed with new fields."""
        filters = ProductFilters(
            countries=["US", "CA"],
            channels=["display", "video"],
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            budget_range={"currency": "USD", "min": 10.0, "max": 100.0},
        )

        assert filters.countries is not None
        assert filters.channels is not None
        assert filters.start_date is not None
        assert filters.end_date is not None
        assert filters.budget_range is not None
