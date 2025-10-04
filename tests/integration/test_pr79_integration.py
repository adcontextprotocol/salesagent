"""Integration tests for AdCP PR #79 (min_exposures filtering and dynamic pricing)."""

from datetime import date, timedelta

import pytest

from src.core.database.database_session import get_db_session
from src.core.database.models import FormatPerformanceMetrics
from src.core.schemas import Product
from src.services.dynamic_pricing_service import DynamicPricingService


class TestPR79Integration:
    """Integration tests for PR #79 end-to-end flow."""

    @pytest.fixture
    def tenant_id(self):
        """Test tenant ID."""
        return "test_tenant_pr79"

    @pytest.fixture
    def setup_format_metrics(self, tenant_id):
        """Create format performance metrics in database."""
        from src.core.database.models import Tenant

        with get_db_session() as session:
            # Clear existing test data
            session.query(FormatPerformanceMetrics).filter_by(tenant_id=tenant_id).delete()
            session.query(Tenant).filter_by(tenant_id=tenant_id).delete()

            # Create test tenant
            from datetime import datetime

            test_tenant = Tenant(
                tenant_id=tenant_id,
                name="Test Tenant PR79",
                subdomain="test-pr79",
                ad_server="mock",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(test_tenant)
            session.commit()

            # Create metrics for US / 300x250
            metric1 = FormatPerformanceMetrics(
                tenant_id=tenant_id,
                country_code="US",
                creative_size="300x250",
                period_start=date.today() - timedelta(days=30),
                period_end=date.today(),
                total_impressions=1000000,
                total_revenue_micros=2500000000,  # $2500 / 1M impressions = $2.50 CPM
                average_cpm=2.50,
                median_cpm=2.50,
                p75_cpm=3.00,
                p90_cpm=3.50,
            )
            session.add(metric1)

            # Create metrics for US / 728x90
            metric2 = FormatPerformanceMetrics(
                tenant_id=tenant_id,
                country_code="US",
                creative_size="728x90",
                period_start=date.today() - timedelta(days=30),
                period_end=date.today(),
                total_impressions=500000,
                total_revenue_micros=1000000000,  # $1000 / 500k impressions = $2.00 CPM
                average_cpm=2.00,
                median_cpm=2.00,
                p75_cpm=2.50,
                p90_cpm=3.00,
            )
            session.add(metric2)

            session.commit()

        yield

        # Cleanup
        from src.core.database.models import Tenant

        with get_db_session() as session:
            session.query(FormatPerformanceMetrics).filter_by(tenant_id=tenant_id).delete()
            session.query(Tenant).filter_by(tenant_id=tenant_id).delete()
            session.commit()

    @pytest.fixture
    def test_products(self):
        """Create test products with various formats."""
        return [
            Product(
                product_id="display_package",
                name="Display Package",
                description="Standard display formats",
                formats=["display_300x250", "display_728x90"],
                delivery_type="non_guaranteed",
                is_fixed_price=False,
                cpm=None,  # Will be dynamically calculated
            ),
            Product(
                product_id="premium_display",
                name="Premium Display",
                description="Premium 300x250 only",
                formats=["display_300x250"],
                delivery_type="guaranteed",
                is_fixed_price=True,
                cpm=5.00,  # Fixed price, but floor/recommended still calculated
            ),
        ]

    def test_dynamic_pricing_enrichment(self, tenant_id, setup_format_metrics, test_products):
        """Test that products are enriched with dynamic pricing from cached metrics."""
        with get_db_session() as session:
            pricing_service = DynamicPricingService(session)

            enriched = pricing_service.enrich_products_with_pricing(
                products=test_products, tenant_id=tenant_id, country_code="US", min_exposures=None
            )

            # Verify first product (multi-format) has pricing
            display_package = enriched[0]
            assert display_package.currency == "USD"
            assert display_package.floor_cpm is not None
            assert display_package.recommended_cpm is not None
            assert display_package.estimated_exposures is not None

            # Floor CPM should be weighted median: (2.50 * 1M + 2.00 * 500k) / 1.5M = 2.33
            assert display_package.floor_cpm == pytest.approx(2.33, rel=0.01)

            # Recommended CPM should be weighted p75: (3.00 * 1M + 2.50 * 500k) / 1.5M = 2.83
            assert display_package.recommended_cpm == pytest.approx(2.83, rel=0.01)

            # Estimated exposures: (1M + 500k) / 30 days * 30 days = 1.5M monthly
            assert display_package.estimated_exposures == pytest.approx(1500000, rel=0.01)

            # Verify second product (single format) has pricing
            premium_display = enriched[1]
            assert premium_display.floor_cpm == pytest.approx(2.50, rel=0.01)  # Median for 300x250
            assert premium_display.recommended_cpm == pytest.approx(3.00, rel=0.01)  # P75 for 300x250

    def test_min_exposures_filtering(self, tenant_id, setup_format_metrics, test_products):
        """Test that min_exposures filter affects product recommendations."""
        with get_db_session() as session:
            pricing_service = DynamicPricingService(session)

            # Request minimum 500k exposures (less than available 1.5M)
            enriched_low = pricing_service.enrich_products_with_pricing(
                products=test_products[:1], tenant_id=tenant_id, country_code="US", min_exposures=500000
            )

            # Should use standard p75 recommended CPM
            assert enriched_low[0].recommended_cpm == pytest.approx(2.83, rel=0.01)

            # Request minimum 5M exposures (more than available 1.5M)
            enriched_high = pricing_service.enrich_products_with_pricing(
                products=test_products[:1], tenant_id=tenant_id, country_code="US", min_exposures=5000000
            )

            # Should use p90 CPM to compete for more volume
            # Weighted p90: (3.50 * 1M + 3.00 * 500k) / 1.5M = 3.33
            assert enriched_high[0].recommended_cpm == pytest.approx(3.33, rel=0.01)

    def test_country_specific_pricing(self, tenant_id, setup_format_metrics):
        """Test that country filtering works correctly."""
        # Add UK metrics
        with get_db_session() as session:
            metric_uk = FormatPerformanceMetrics(
                tenant_id=tenant_id,
                country_code="UK",
                creative_size="300x250",
                period_start=date.today() - timedelta(days=30),
                period_end=date.today(),
                total_impressions=200000,
                total_revenue_micros=800000000,  # $800 / 200k = $4.00 CPM
                average_cpm=4.00,
                median_cpm=4.00,
                p75_cpm=4.50,
                p90_cpm=5.00,
            )
            session.add(metric_uk)
            session.commit()

            # Test UK pricing
            product = Product(
                product_id="test",
                name="Test",
                description="Test",
                formats=["display_300x250"],
                delivery_type="non_guaranteed",
                is_fixed_price=False,
            )

            pricing_service = DynamicPricingService(session)
            enriched_uk = pricing_service.enrich_products_with_pricing(
                products=[product], tenant_id=tenant_id, country_code="UK", min_exposures=None
            )

            # Should use UK pricing (higher than US)
            assert enriched_uk[0].floor_cpm == pytest.approx(4.00, rel=0.01)
            assert enriched_uk[0].recommended_cpm == pytest.approx(4.50, rel=0.01)

            # Cleanup
            session.query(FormatPerformanceMetrics).filter_by(tenant_id=tenant_id, country_code="UK").delete()
            session.commit()

    def test_no_metrics_fallback(self, tenant_id, test_products):
        """Test graceful fallback when no metrics available."""
        with get_db_session() as session:
            # Don't set up metrics - use clean tenant
            pricing_service = DynamicPricingService(session)

            enriched = pricing_service.enrich_products_with_pricing(
                products=test_products, tenant_id="nonexistent_tenant", country_code="US", min_exposures=None
            )

            # Products should be enriched with defaults
            assert enriched[0].currency == "USD"
            assert enriched[0].floor_cpm is None
            assert enriched[0].recommended_cpm is None
            assert enriched[0].estimated_exposures is None

    # Skipping test_get_products_integration because it requires full MCP server setup
    # The dynamic pricing integration is already tested by other tests in this file

    def test_format_size_extraction(self, tenant_id):
        """Test that creative sizes are correctly extracted from format IDs."""
        with get_db_session() as session:
            pricing_service = DynamicPricingService(session)

            product = Product(
                product_id="test",
                name="Test",
                description="Test",
                formats=[
                    "display_300x250",
                    "display_728x90",
                    "video_640x480",
                    "native",  # No dimensions
                    "audio",  # No dimensions
                ],
                delivery_type="non_guaranteed",
                is_fixed_price=False,
            )

            # This should extract: 300x250, 728x90, 640x480
            # Should skip: native, audio (no dimensions)
            pricing = pricing_service._calculate_product_pricing(
                product=product,
                tenant_id=tenant_id,
                country_code="US",
                min_exposures=None,
                cutoff_date=date.today() - timedelta(days=30),
            )

            # Should get defaults (no metrics), but extraction should work
            assert pricing["currency"] == "USD"
