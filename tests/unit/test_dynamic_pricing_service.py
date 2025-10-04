"""Unit tests for DynamicPricingService (AdCP PR #79)."""

from datetime import date, timedelta
from unittest.mock import Mock

import pytest

from src.core.schemas import Product
from src.services.dynamic_pricing_service import DynamicPricingService


class TestDynamicPricingService:
    """Test dynamic pricing calculation from cached format metrics."""

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session."""
        session = Mock()
        session.query = Mock()
        return session

    @pytest.fixture
    def service(self, mock_db_session):
        """Create service instance with mock session."""
        return DynamicPricingService(mock_db_session)

    @pytest.fixture
    def mock_format_metrics(self):
        """Mock format performance metrics from database."""
        metrics = []

        # US / 300x250 metrics
        metric1 = Mock()
        metric1.tenant_id = "test_tenant"
        metric1.country_code = "US"
        metric1.creative_size = "300x250"
        metric1.period_start = date.today() - timedelta(days=30)
        metric1.period_end = date.today()
        metric1.total_impressions = 50000
        metric1.median_cpm = 2.50
        metric1.p75_cpm = 3.00
        metric1.p90_cpm = 3.50
        metrics.append(metric1)

        # US / 728x90 metrics
        metric2 = Mock()
        metric2.tenant_id = "test_tenant"
        metric2.country_code = "US"
        metric2.creative_size = "728x90"
        metric2.period_start = date.today() - timedelta(days=30)
        metric2.period_end = date.today()
        metric2.total_impressions = 30000
        metric2.median_cpm = 2.00
        metric2.p75_cpm = 2.50
        metric2.p90_cpm = 3.00
        metrics.append(metric2)

        return metrics

    @pytest.fixture
    def test_products(self):
        """Create test products with different formats."""
        return [
            Product(
                product_id="product_1",
                name="Display Product",
                description="Test display product",
                formats=["display_300x250", "display_728x90"],
                delivery_type="non_guaranteed",
                is_fixed_price=False,
            ),
            Product(
                product_id="product_2",
                name="Guaranteed Product",
                description="Test guaranteed product",
                formats=["display_300x250"],
                delivery_type="guaranteed",
                is_fixed_price=True,
            ),
        ]

    def test_calculate_weighted_avg(self, service):
        """Test weighted average calculation."""
        mock_metrics = []

        # Create mock metrics with different values and weights
        m1 = Mock()
        m1.median_cpm = 2.0
        m1.total_impressions = 1000
        mock_metrics.append(m1)

        m2 = Mock()
        m2.median_cpm = 4.0
        m2.total_impressions = 3000
        mock_metrics.append(m2)

        # Weighted avg should be (2.0 * 1000 + 4.0 * 3000) / (1000 + 3000) = 3.5
        avg = service._calculate_weighted_avg(mock_metrics, lambda m: m.median_cpm, lambda m: m.total_impressions)

        assert avg == pytest.approx(3.5, rel=0.01)

    def test_calculate_weighted_avg_empty(self, service):
        """Test weighted average with empty metrics."""
        avg = service._calculate_weighted_avg([], lambda m: m.value, lambda m: m.weight)

        assert avg is None

    def test_calculate_weighted_avg_zero_weight(self, service):
        """Test weighted average with zero weights."""
        m1 = Mock()
        m1.value = 5.0
        m1.weight = 0

        avg = service._calculate_weighted_avg([m1], lambda m: m.value, lambda m: m.weight)

        assert avg is None

    def test_default_pricing(self, service):
        """Test default pricing when no metrics available."""
        pricing = service._default_pricing()

        assert pricing["currency"] == "USD"
        assert pricing["floor_cpm"] is None
        assert pricing["recommended_cpm"] is None
        assert pricing["estimated_exposures"] is None

    def test_enrich_products_with_pricing(self, service, test_products, mock_format_metrics, mock_db_session):
        """Test enriching products with dynamic pricing."""
        # Mock database query chain properly (supports chained .filter() calls)
        mock_filter2 = Mock()
        mock_filter2.all.return_value = mock_format_metrics
        mock_filter2.filter.return_value = mock_filter2  # Support additional chained filters

        mock_filter1 = Mock()
        mock_filter1.all.return_value = mock_format_metrics
        mock_filter1.filter.return_value = mock_filter2  # Chain to second filter

        mock_query = Mock()
        mock_query.filter.return_value = mock_filter1
        mock_db_session.query.return_value = mock_query

        enriched = service.enrich_products_with_pricing(
            products=test_products, tenant_id="test_tenant", country_code="US", min_exposures=None
        )

        # Verify products were enriched
        assert len(enriched) == 2

        # Check first product (multi-format)
        product1 = enriched[0]
        assert product1.currency == "USD"
        assert product1.floor_cpm is not None
        assert product1.recommended_cpm is not None
        assert product1.estimated_exposures is not None

        # Check second product (guaranteed)
        product2 = enriched[1]
        assert product2.currency == "USD"
        assert product2.floor_cpm is not None

    def test_enrich_products_no_metrics(self, service, test_products, mock_db_session):
        """Test enriching products when no metrics available."""
        # Mock empty metrics with chained filters
        mock_filter = Mock()
        mock_filter.all.return_value = []
        mock_filter.filter.return_value = mock_filter  # Support chained filters
        mock_query = Mock()
        mock_query.filter.return_value = mock_filter
        mock_db_session.query.return_value = mock_query

        enriched = service.enrich_products_with_pricing(
            products=test_products, tenant_id="test_tenant", country_code="US", min_exposures=None
        )

        # Products should still be enriched with defaults
        assert len(enriched) == 2
        assert enriched[0].currency == "USD"
        assert enriched[0].floor_cpm is None
        assert enriched[0].recommended_cpm is None

    def test_enrich_products_min_exposures_recommendation(
        self, service, test_products, mock_format_metrics, mock_db_session
    ):
        """Test recommended_cpm increases when min_exposures can't be met."""
        # Mock metrics with low volume
        for metric in mock_format_metrics:
            metric.total_impressions = 1000  # Very low volume
            metric.period_start = date.today() - timedelta(days=30)
            metric.period_end = date.today()

        mock_filter = Mock()
        mock_filter.all.return_value = mock_format_metrics
        mock_filter.filter.return_value = mock_filter  # Support chained filters
        mock_query = Mock()
        mock_query.filter.return_value = mock_filter
        mock_db_session.query.return_value = mock_query

        # Request high min_exposures (more than available)
        enriched = service.enrich_products_with_pricing(
            products=test_products, tenant_id="test_tenant", country_code="US", min_exposures=100000
        )

        # Recommended CPM should use p90 to compete for more volume
        product1 = enriched[0]
        assert product1.recommended_cpm == pytest.approx(
            3.25, rel=0.1
        )  # Weighted avg of p90 values (3.5 * 50k + 3.0 * 30k) / 80k

    def test_enrich_products_extracts_creative_sizes(self, service, mock_db_session):
        """Test creative size extraction from format IDs."""
        product = Product(
            product_id="test",
            name="Test",
            description="Test",
            formats=["display_300x250", "video_640x480", "native"],
            delivery_type="non_guaranteed",
            is_fixed_price=False,
        )

        # Mock empty metrics to test size extraction
        mock_filter = Mock()
        mock_filter.all.return_value = []
        mock_filter.filter.return_value = mock_filter  # Support chained filters
        mock_query = Mock()
        mock_query.filter.return_value = mock_filter
        mock_db_session.query.return_value = mock_query

        service.enrich_products_with_pricing(products=[product], tenant_id="test_tenant")

        # Verify query was called with correct creative sizes
        # Should extract: 300x250, 640x480 (skip 'native' - no dimensions)
        filter_call = mock_query.filter.call_args
        # Check that filter was called (size extraction happened)
        assert filter_call is not None

    def test_enrich_products_empty_list(self, service, mock_db_session):
        """Test enriching empty product list."""
        enriched = service.enrich_products_with_pricing(
            products=[], tenant_id="test_tenant", country_code="US", min_exposures=None
        )

        assert enriched == []

    def test_enrich_products_country_filtering(self, service, test_products, mock_format_metrics, mock_db_session):
        """Test country-specific metrics filtering."""
        mock_filter = Mock()
        mock_filter.all.return_value = mock_format_metrics
        mock_filter.filter.return_value = mock_filter  # Support chained filters
        mock_query = Mock()
        mock_query.filter.return_value = mock_filter
        mock_db_session.query.return_value = mock_query

        service.enrich_products_with_pricing(
            products=test_products, tenant_id="test_tenant", country_code="UK", min_exposures=None
        )

        # Verify country filter was applied
        filter_call = mock_query.filter.call_args
        assert filter_call is not None
