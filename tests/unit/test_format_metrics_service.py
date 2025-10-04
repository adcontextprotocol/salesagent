"""Unit tests for FormatMetricsAggregationService (AdCP PR #79)."""

from unittest.mock import Mock, patch

import pytest

from src.services.format_metrics_service import FormatMetricsAggregationService


class TestFormatMetricsAggregationService:
    """Test format metrics aggregation from GAM reporting."""

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session."""
        session = Mock()
        session.query = Mock()
        session.add = Mock()
        session.commit = Mock()
        return session

    @pytest.fixture
    def service(self, mock_db_session):
        """Create service instance with mock session."""
        return FormatMetricsAggregationService(mock_db_session)

    @pytest.fixture
    def mock_gam_report_data(self):
        """Mock GAM report response with realistic data."""
        return [
            {
                "dimensionValues": [
                    {"value": "US"},  # COUNTRY_CODE
                    {"value": "300x250"},  # CREATIVE_SIZE
                ],
                "metricValues": [
                    {"value": "50000"},  # AD_SERVER_IMPRESSIONS
                    {"value": "250"},  # AD_SERVER_CLICKS
                    {"value": "125000000"},  # AD_SERVER_CPM_AND_CPC_REVENUE (micros)
                ],
            },
            {
                "dimensionValues": [
                    {"value": "US"},
                    {"value": "728x90"},
                ],
                "metricValues": [
                    {"value": "30000"},
                    {"value": "150"},
                    {"value": "90000000"},
                ],
            },
            {
                "dimensionValues": [
                    {"value": "UK"},
                    {"value": "300x250"},
                ],
                "metricValues": [
                    {"value": "20000"},
                    {"value": "100"},
                    {"value": "60000000"},
                ],
            },
        ]

    def test_calculate_percentile(self, service):
        """Test percentile calculation."""
        # Line item CPMs (in dollars)
        line_item_cpms = sorted([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])

        # Test median (50th percentile) - should be 5.5
        median = service._calculate_percentile(line_item_cpms, 50)
        assert median == pytest.approx(5.5, rel=0.01)

        # Test p75 (75th percentile) - should be 7.75
        p75 = service._calculate_percentile(line_item_cpms, 75)
        assert p75 == pytest.approx(7.75, rel=0.01)

        # Test p90 (90th percentile) - should be 9.1
        p90 = service._calculate_percentile(line_item_cpms, 90)
        assert p90 == pytest.approx(9.1, rel=0.01)

    def test_calculate_percentile_empty(self, service):
        """Test percentile calculation with empty data."""
        result = service._calculate_percentile([], 50)
        assert result is None

    def test_calculate_percentile_single_value(self, service):
        """Test percentile calculation with single value."""
        result = service._calculate_percentile([5.0], 50)
        assert result == 5.0

    @patch("src.services.format_metrics_service.FormatMetricsAggregationService._query_format_metrics")
    def test_aggregate_metrics_for_tenant(self, mock_query, service, mock_db_session):
        """Test full aggregation flow for a tenant."""
        # Mock _query_format_metrics to return processed data in expected format
        mock_query.return_value = [
            {
                "country_code": "US",
                "creative_size": "300x250",
                "impressions": 50000,
                "clicks": 250,
                "revenue_micros": 125000000,
            },
            {
                "country_code": "US",
                "creative_size": "728x90",
                "impressions": 30000,
                "clicks": 150,
                "revenue_micros": 90000000,
            },
            {
                "country_code": "UK",
                "creative_size": "300x250",
                "impressions": 20000,
                "clicks": 100,
                "revenue_micros": 60000000,
            },
        ]
        mock_gam_client = Mock()

        # Mock database query for existing metrics
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        summary = service.aggregate_metrics_for_tenant(
            tenant_id="test_tenant", gam_client=mock_gam_client, period_days=30
        )

        # Verify query was called
        mock_query.assert_called_once()

        # Verify summary data
        assert summary["rows_created"] == 3  # US/300x250, US/728x90, UK/300x250
        assert summary["rows_updated"] == 0
        assert summary["formats_processed"] == 3

        # Verify database adds were called for each unique country+format
        assert mock_db_session.add.call_count == 3
        assert mock_db_session.commit.call_count == 1

    @patch("src.services.format_metrics_service.FormatMetricsAggregationService._query_format_metrics")
    def test_aggregate_metrics_update_existing(self, mock_query, service, mock_db_session):
        """Test updating existing metrics."""
        mock_query.return_value = [
            {
                "country_code": "US",
                "creative_size": "300x250",
                "impressions": 50000,
                "clicks": 250,
                "revenue_micros": 125000000,
            },
            {
                "country_code": "US",
                "creative_size": "728x90",
                "impressions": 30000,
                "clicks": 150,
                "revenue_micros": 90000000,
            },
            {
                "country_code": "UK",
                "creative_size": "300x250",
                "impressions": 20000,
                "clicks": 100,
                "revenue_micros": 60000000,
            },
        ]
        mock_gam_client = Mock()

        # Mock existing metric that should be updated
        existing_metric = Mock()
        existing_metric.total_impressions = 10000
        mock_db_session.query.return_value.filter.return_value.first.return_value = existing_metric

        summary = service.aggregate_metrics_for_tenant(
            tenant_id="test_tenant", gam_client=mock_gam_client, period_days=30
        )

        # Should update existing records, not create new ones
        assert summary["rows_created"] == 0
        assert summary["rows_updated"] == 3

        # Verify commit was called
        assert mock_db_session.commit.call_count == 1

    def test_aggregate_metrics_error_handling(self, service, mock_db_session):
        """Test error handling in aggregation."""
        mock_gam_client = Mock()
        # Error would happen in _query_format_metrics when trying to use GAM client
        with patch.object(service, "_query_format_metrics", side_effect=Exception("GAM API Error")):
            with pytest.raises(Exception, match="GAM API Error"):
                service.aggregate_metrics_for_tenant(
                    tenant_id="test_tenant", gam_client=mock_gam_client, period_days=30
                )
